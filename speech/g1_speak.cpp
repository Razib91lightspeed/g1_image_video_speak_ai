#include <iostream>
#include <string>
#include <thread>
#include <chrono>
#include <cstdint>

#include <unitree/robot/channel/channel_factory.hpp>
#include <unitree/robot/g1/audio/g1_audio_client.hpp>

int main(int argc, char* argv[]) {

    std::string message =
        "Welcome to Tampere University of Applied Sciences. "
        "Have you been enjoying so far? I bet you are.";

    // Accept custom speech from the terminal
    if (argc > 1) {
        message.clear();

        for (int i = 1; i < argc; ++i) {
            if (i > 1) message += " ";
            message += argv[i];
        }
    }

    std::cout << "Connecting to G1 audio service..." << std::endl;

    // G1's working internal network interface
    unitree::robot::ChannelFactory::Instance()->Init(0, "enp2s0f0");

    unitree::robot::g1::AudioClient audio;
    audio.Init();
    audio.SetTimeout(10.0f);

    uint8_t volume = 0;
    int ret = audio.GetVolume(volume);

    std::cout << "GetVolume result: " << ret << std::endl;

    if (ret == 0) {
        std::cout << "Current volume: "
                  << static_cast<int>(volume) << std::endl;

        if (volume < 50) {
            ret = audio.SetVolume(60);
            std::cout << "SetVolume result: " << ret << std::endl;
        }
    }

    std::cout << "G1, say: " << message << std::endl;

    ret = audio.TtsMaker(message, 1);

    std::cout << "TtsMaker result: " << ret << std::endl;

    if (ret != 0) {
        std::cerr << "Speech request failed." << std::endl;
        return 1;
    }

    std::this_thread::sleep_for(std::chrono::seconds(8));

    std::cout << "Speech request completed." << std::endl;
    return 0;
}
