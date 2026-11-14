#include <unitree/robot/channel/channel_factory.hpp>
#include <unitree/robot/g1/audio/g1_audio_client.hpp>

#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>
#include <csignal>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <string>

static volatile std::sig_atomic_t interrupted = 0;

void handle_signal(int) {
    interrupted = 1;
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

int main() {
    std::signal(SIGINT, handle_signal);
    std::signal(SIGTERM, handle_signal);

    unitree::robot::ChannelFactory::Instance()->Init(0, "eth0");

    MicClient client;
    client.InitMic();
    client.SetTimeout(3.0f);

    std::string response;

    if (client.GetMode(response) != 0) {
        std::cerr << "Cannot read microphone mode\n";
        return 1;
    }

    std::cout << "Initial microphone mode: "
              << response << std::endl;

    // This experiment expects the previously verified OFF state.
    if (response.find("\"mode\":2") == std::string::npos) {
        std::cerr << "STOP: Microphone mode is not 2.\n";
        std::cerr << "No changes made.\n";
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
             sizeof(address)) < 0) {
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
                   &membership, sizeof(membership)) < 0) {
        perror("multicast join");
        close(sock);
        return 1;
    }

    timeval timeout{};
    timeout.tv_sec = 0;
    timeout.tv_usec = 250000;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO,
               &timeout, sizeof(timeout));

    std::cout << "Activating microphone temporarily..."
              << std::endl;

    response.clear();
    int result = client.SetMode(1, response);

    std::cout << "Activation result: " << result
              << " Response: " << response << std::endl;

    if (result != 0) {
        std::cerr << "Activation failed or was rejected.\n";
        // Request the original OFF mode as a precaution.
        std::string restore_response;
        int restore = client.SetMode(2, restore_response);
        std::cout << "Restore request result: "
                  << restore << std::endl;
        close(sock);
        return 1;
    }

    std::cout << "Listening for 8 seconds. Speak near G1."
              << std::endl;

    size_t packets = 0;
    size_t bytes = 0;
    char buffer[8192];

    auto deadline = std::chrono::steady_clock::now() +
                    std::chrono::seconds(8);

    while (!interrupted &&
           std::chrono::steady_clock::now() < deadline) {
        ssize_t n = recv(sock, buffer, sizeof(buffer), 0);

        if (n > 0) {
            ++packets;
            bytes += static_cast<size_t>(n);

            if (packets <= 5) {
                std::cout << "Packet " << packets
                          << ": " << n << " bytes"
                          << std::endl;
            }
        }
    }

    std::cout << "Packets received: " << packets << std::endl;
    std::cout << "Total bytes: " << bytes << std::endl;

    std::cout << "Restoring original mode 2..."
              << std::endl;

    response.clear();
    result = client.SetMode(2, response);

    std::cout << "Restore result: " << result
              << " Response: " << response << std::endl;

    std::string final_mode;
    int status = client.GetMode(final_mode);

    std::cout << "Final status result: " << status
              << " Mode: " << final_mode << std::endl;

    close(sock);

    if (result != 0 || status != 0 ||
        final_mode.find("\"mode\":2") == std::string::npos) {
        std::cerr << "WARNING: Original microphone mode "
                     "was not confirmed restored.\n";
        return 1;
    }

    std::cout << "Microphone returned to original state."
              << std::endl;

    return packets > 0 ? 0 : 2;
}
