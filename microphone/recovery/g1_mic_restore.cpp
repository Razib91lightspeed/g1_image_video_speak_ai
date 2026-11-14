#include <unitree/robot/channel/channel_factory.hpp>
#include <unitree/robot/g1/audio/g1_audio_client.hpp>

#include <chrono>
#include <cstdint>
#include <iostream>
#include <string>
#include <thread>

class MicRecovery : public unitree::robot::g1::AudioClient {
public:
    void InitRecovery() {
        Init();
        RegistApi(1007, 0);
        RegistApi(1008, 0);
        SetTimeout(3.0f);
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
    unitree::robot::ChannelFactory::Instance()->Init(0, "eth0");

    MicRecovery client;
    client.InitRecovery();

    std::string response;

    int result = client.GetMode(response);

    std::cout << "Initial mode: " << response << std::endl;

    if (result != 0) {
        std::cerr << "Unable to read microphone mode." << std::endl;
        return 1;
    }

    if (response.find("\"mode\":2") != std::string::npos) {
        std::cout << "Already in mode 2. No change required."
                  << std::endl;
        return 0;
    }

    if (response.find("\"mode\":1") == std::string::npos) {
        std::cerr << "Unexpected mode. No changes made."
                  << std::endl;
        return 1;
    }

    response.clear();
    result = client.SetMode(2, response);

    std::cout << "Restore request result: "
              << result << std::endl;

    if (result != 0) {
        std::cerr << "Restore request failed." << std::endl;
        return 1;
    }

    for (int i = 0; i < 12; ++i) {
        std::this_thread::sleep_for(
            std::chrono::milliseconds(500)
        );

        response.clear();
        result = client.GetMode(response);

        std::cout << "Status: " << response << std::endl;

        if (result == 0 &&
            response.find("\"mode\":2") != std::string::npos) {
            std::cout << "RESTORE CONFIRMED: mode 2"
                      << std::endl;
            return 0;
        }
    }

    std::cerr << "WARNING: Mode 2 not confirmed."
              << std::endl;

    return 1;
}
