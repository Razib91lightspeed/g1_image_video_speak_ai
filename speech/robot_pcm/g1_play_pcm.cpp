#include <unitree/robot/channel/channel_factory.hpp>
#include <unitree/robot/g1/audio/g1_audio_client.hpp>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <thread>
#include <vector>

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "Usage: g1_play_pcm <16k_mono_s16le.pcm>\n";
        return 1;
    }

    std::ifstream file(argv[1], std::ios::binary);
    if (!file) {
        std::cerr << "Cannot open PCM file\n";
        return 1;
    }

    std::vector<uint8_t> pcm(
        (std::istreambuf_iterator<char>(file)),
        std::istreambuf_iterator<char>()
    );

    if (pcm.empty() || pcm.size() % 2 != 0) {
        std::cerr << "Invalid PCM data\n";
        return 1;
    }

    const double duration = pcm.size() / 32000.0;
    if (duration > 30.0) {
        std::cerr << "First test limited to 30 seconds\n";
        return 1;
    }

    unitree::robot::ChannelFactory::Instance()->Init(0, "eth0");

    unitree::robot::g1::AudioClient audio;
    audio.Init();
    audio.SetTimeout(10.0f);

    const std::string app = "g1_visual_assistant";
    const std::string stream_id =
        std::to_string(
            std::chrono::steady_clock::now()
                .time_since_epoch().count()
        );

    const size_t chunk_size = 16000; // 0.5 seconds of PCM
    size_t offset = 0;

    std::cout << "Starting G1 native audio playback\n";
    std::cout << "Duration: " << duration << " seconds\n";

    while (offset < pcm.size()) {
        size_t end = std::min(offset + chunk_size, pcm.size());

        std::vector<uint8_t> chunk(
            pcm.begin() + offset, pcm.begin() + end
        );

        int ret = audio.PlayStream(app, stream_id, chunk);

        std::cout << "PlayStream result: " << ret << std::endl;

        if (ret != 0) {
            audio.PlayStop(app);
            return 1;
        }

        offset = end;

        std::this_thread::sleep_for(
            std::chrono::milliseconds(500)
        );
    }

    std::this_thread::sleep_for(
        std::chrono::milliseconds(700)
    );

    audio.PlayStop(app);

    std::cout << "Playback request complete\n";
    return 0;
}
