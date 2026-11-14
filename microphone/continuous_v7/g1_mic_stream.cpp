#include <unitree/robot/channel/channel_factory.hpp>
#include <unitree/robot/g1/audio/g1_audio_client.hpp>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>
#include <cerrno>
#include <csignal>
#include <chrono>
#include <iostream>
#include <string>
#include <thread>

static volatile std::sig_atomic_t stop_requested = 0;
void handle_signal(int) { stop_requested = 1; }

class MicClient : public unitree::robot::g1::AudioClient {
public:
    void InitMic() { Init(); RegistApi(1007, 0); RegistApi(1008, 0); }
    int Status(std::string& result) { return Call(1007, "{}", result); }
    int SetMode(int mode) {
        std::string result;
        return Call(1008, "{\"mode\":" + std::to_string(mode) + "}", result);
    }
};

bool mode_is(MicClient& c, int value) {
    std::string s;
    return c.Status(s) == 0 && s.find("\"mode\":" + std::to_string(value)) != std::string::npos;
}

bool restore(MicClient& c) {
    for (int attempt = 0; attempt < 3; ++attempt) {
        int rc = c.SetMode(2);
        std::cerr << "Restore request " << attempt + 1 << " result=" << rc << '\n';
        for (int i = 0; i < 12; ++i) {
            std::this_thread::sleep_for(std::chrono::milliseconds(500));
            if (mode_is(c, 2)) {
                std::cerr << "RESTORE CONFIRMED: mode 2\n";
                return true;
            }
        }
    }
    std::cerr << "WARNING: mode 2 restoration NOT confirmed\n";
    return false;
}

int main() {
    std::signal(SIGINT, handle_signal);
    std::signal(SIGTERM, handle_signal);
    std::signal(SIGPIPE, SIG_IGN);
    unitree::robot::ChannelFactory::Instance()->Init(0, "eth0");
    MicClient client;
    client.InitMic();
    client.SetTimeout(3.0f);
    if (!mode_is(client, 2)) {
        std::cerr << "STOP: initial microphone mode is not 2\n";
        return 1;
    }
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) { perror("socket"); return 1; }
    int reuse = 1;
    setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(5555);
    addr.sin_addr.s_addr = INADDR_ANY;
    if (bind(sock, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        perror("bind"); close(sock); return 1;
    }
    ip_mreq member{};
    inet_pton(AF_INET, "239.168.123.161", &member.imr_multiaddr);
    inet_pton(AF_INET, "192.168.123.164", &member.imr_interface);
    if (setsockopt(sock, IPPROTO_IP, IP_ADD_MEMBERSHIP, &member, sizeof(member)) < 0) {
        perror("multicast join"); close(sock); return 1;
    }
    timeval timeout{};
    timeout.tv_usec = 250000;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    int activated = client.SetMode(1);
    std::cerr << "Activation result=" << activated << '\n';
    bool success = activated == 0;
    if (success) {
        std::cerr << "PCM STREAM ACTIVE (16kHz mono signed 16-bit)\n";
        auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(600);
        unsigned char packet[8192];
        while (!stop_requested && std::chrono::steady_clock::now() < deadline) {
            ssize_t n = recv(sock, packet, sizeof(packet), 0);
            if (n < 0) {
                if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) continue;
                perror("recv"); success = false; break;
            }
            if (n != 5120) continue;
            size_t offset = 0;
            while (offset < static_cast<size_t>(n) && !stop_requested) {
                ssize_t sent = write(STDOUT_FILENO, packet + offset, static_cast<size_t>(n) - offset);
                if (sent < 0) {
                    if (errno == EINTR) continue;
                    success = false;
                    stop_requested = 1;
                    break;
                }
                offset += static_cast<size_t>(sent);
            }
        }
    }
    close(sock);
    bool restored = restore(client);
    return success && restored ? 0 : 1;
}
