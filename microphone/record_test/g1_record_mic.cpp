#include <unitree/robot/channel/channel_factory.hpp>
#include <unitree/robot/g1/audio/g1_audio_client.hpp>

#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

static volatile std::sig_atomic_t stopped = 0;

void signal_handler(int) {
    stopped = 1;
}

class MicClient : public unitree::robot::g1::AudioClient {
public:
    void InitMic() {
        Init();
        RegistApi(1007, 0);
        RegistApi(1008, 0);
    }

    int GetMode(std::string& response) {
        return Call(1007, "{}", response);
    }

    int SetMode(int mode, std::string& response) {
        return Call(
            1008,
            "{\"mode\":" + std::to_string(mode) + "}",
            response
        );
    }
};

bool is_mode_2(MicClient& client) {
    std::string response;
    int result = client.GetMode(response);

    std::cerr << "Mode check: " << result
              << " " << response << std::endl;

    return result == 0 &&
           response.find("\"mode\":2") != std::string::npos;
}

bool restore_mode_2(MicClient& client) {
    std::cerr << "Restoring microphone mode 2..."
              << std::endl;

    for (int attempt = 0; attempt < 3; ++attempt) {
        std::string response;
        int result = client.SetMode(2, response);

        std::cerr << "Restore request: "
                  << result << " " << response << std::endl;

        for (int check = 0; check < 12; ++check) {
            std::this_thread::sleep_for(
                std::chrono::milliseconds(500)
            );

            if (is_mode_2(client)) {
                std::cerr << "RESTORE CONFIRMED: mode 2"
                          << std::endl;
                return true;
            }
        }
    }

    std::cerr << "WARNING: Restoration NOT confirmed"
              << std::endl;
    return false;
}

int main() {
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    std::signal(SIGPIPE, SIG_IGN);

    unitree::robot::ChannelFactory::Instance()->Init(0, "eth0");

    MicClient client;
    client.InitMic();
    client.SetTimeout(3.0f);

    std::cerr << "===== G1 MICROPHONE RECORDING ====="
              << std::endl;

    if (!is_mode_2(client)) {
        std::cerr << "STOP: Initial mode is not 2"
                  << std::endl;
        return 1;
    }

    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        perror("socket");
        return 1;
    }

    int reuse = 1;
    setsockopt(sock, SOL_SOCKET, SO_REUSEADDR,
               &reuse, sizeof(reuse));

    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_port = htons(5555);
    address.sin_addr.s_addr = INADDR_ANY;

    if (bind(sock, reinterpret_cast<sockaddr*>(&address),
             sizeof(address)) != 0) {
        perror("bind");
        close(sock);
        return 1;
    }

    ip_mreq membership{};
    inet_pton(AF_INET, "239.168.123.161",
              &membership.imr_multiaddr);
    inet_pton(AF_INET, "192.168.123.164",
              &membership.imr_interface);

    if (setsockopt(sock, IPPROTO_IP, IP_ADD_MEMBERSHIP,
                   &membership, sizeof(membership)) != 0) {
        perror("multicast");
        close(sock);
        return 1;
    }

    timeval timeout{};
    timeout.tv_sec = 0;
    timeout.tv_usec = 250000;

    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO,
               &timeout, sizeof(timeout));

    std::vector<uint8_t> recording;
    recording.reserve(160000);

    std::string response;

    // From this point onward, always attempt restoration.
    std::cerr << "Activating microphone..." << std::endl;

    int activation = client.SetMode(1, response);

    std::cerr << "Activation result: "
              << activation << std::endl;

    if (activation == 0) {
        std::cerr << "SPEAK NOW: Say 'Hey Buddy, can you hear me?'"
                  << std::endl;

        const size_t target_bytes = 16000 * 2 * 5;

        auto deadline = std::chrono::steady_clock::now() +
                        std::chrono::seconds(10);

        uint8_t buffer[8192];
        size_t packets = 0;

        while (!stopped &&
               recording.size() < target_bytes &&
               std::chrono::steady_clock::now() < deadline) {

            ssize_t n = recv(sock, buffer, sizeof(buffer), 0);

            if (n > 0) {
                size_t available = target_bytes - recording.size();
                size_t count = std::min(
                    static_cast<size_t>(n), available
                );

                recording.insert(
                    recording.end(), buffer, buffer + count
                );

                packets++;
            }
        }

        std::cerr << "Packets received: "
                  << packets << std::endl;

        std::cerr << "Audio bytes: "
                  << recording.size() << std::endl;
    }

    close(sock);

    bool restored = restore_mode_2(client);

    if (!restored || activation != 0 ||
        stopped || recording.size() != 160000) {
        std::cerr << "Recording failed or incomplete."
                  << std::endl;
        return 1;
    }

    // Standard output contains ONLY raw microphone PCM.
    std::cout.write(
        reinterpret_cast<const char*>(recording.data()),
        recording.size()
    );

    std::cout.flush();

    if (!std::cout.good()) {
        std::cerr << "Failed to transfer PCM data"
                  << std::endl;
        return 1;
    }

    std::cerr << "RECORDING SUCCESSFUL" << std::endl;
    return 0;
}
