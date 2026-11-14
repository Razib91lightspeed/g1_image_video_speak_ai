#include <unitree/robot/channel/channel_factory.hpp>
#include <unitree/robot/g1/audio/g1_audio_client.hpp>

#include <cstdint>
#include <iostream>
#include <string>

class MicStatusClient : public unitree::robot::g1::AudioClient {
public:
    void InitStatus() {
        Init();
        RegistApi(1007, 0);
    }

    int32_t GetMicStatus(std::string& response) {
        return Call(1007, "{}", response);
    }
};

int main() {
    std::cout << "===== G1 MICROPHONE STATUS =====" << std::endl;

    unitree::robot::ChannelFactory::Instance()->Init(0, "eth0");

    MicStatusClient client;
    client.InitStatus();
    client.SetTimeout(3.0f);

    std::string response;
    int32_t result = client.GetMicStatus(response);

    std::cout << "API ID: 1007" << std::endl;
    std::cout << "Return code: " << result << std::endl;
    std::cout << "Response: " << response << std::endl;

    if (result == 0) {
        std::cout << "Microphone status request accepted." << std::endl;
    } else {
        std::cout << "Microphone status request failed or unsupported."
                  << std::endl;
    }

    return result == 0 ? 0 : 1;
}
