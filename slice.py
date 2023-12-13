import argparse
import os
import shutil

import torch
from pydub import AudioSegment
from tqdm import tqdm

vad_model, utils = torch.hub.load(
    repo_or_dir="snakers4/silero-vad",
    model="silero_vad",
    onnx=True,
)

(get_speech_timestamps, _, read_audio, *_) = utils


def get_stamps(audio_file, min_silence_dur_ms=700, min_sec=2):
    """
    min_silence_dur_ms:
        このミリ秒数以上を無音だと判断する。
        逆に、この秒数以下の無音区間では区切られない。
        小さくすると、音声がぶつ切りに小さくなりすぎ、
        大きくすると音声一つ一つが長くなりすぎる。
        データセットによってたぶん要調整。
    min_sec:
        この秒数より小さい発話は無視する。TTSのためには2秒未満は切り捨てたほうがいいかも。
    """

    sampling_rate = 16000  # 16kHzか8kHzのみ対応

    wav = read_audio(audio_file, sampling_rate=sampling_rate)
    speech_timestamps = get_speech_timestamps(
        wav,
        vad_model,
        sampling_rate=sampling_rate,
        min_silence_duration_ms=min_silence_dur_ms,
        min_speech_duration_ms=min_sec * 1000,
    )

    return speech_timestamps


def split_wav(
    audio_file, target_dir="/content/slice-and-transcribe/raw", max_sec=12, min_silence_dur_ms=700, min_sec=2
):
    margin = 200  # ミリ秒単位で、音声の前後に余裕を持たせる
    upper_bound_ms = max_sec * 1000  # これ以上の長さの音声は無視する

    speech_timestamps = get_stamps(
        audio_file, min_silence_dur_ms=min_silence_dur_ms, min_sec=min_sec
    )

    # WAVファイルを読み込む
    audio = AudioSegment.from_wav(audio_file)

    # リサンプリング（44100Hz）
    audio = audio.set_frame_rate(44100)

    # ステレオをモノラルに変換
    audio = audio.set_channels(1)

    total_ms = len(audio)

    file_name = os.path.basename(audio_file).split(".")[0]
    os.makedirs(target_dir, exist_ok=True)

    total_time_ms = 0

    # タイムスタンプに従って分割し、ファイルに保存
    for i, ts in enumerate(speech_timestamps):
        start_ms = max(ts["start"] / 16 - margin, 0)
        end_ms = min(ts["end"] / 16 + margin, total_ms)
        if end_ms - start_ms > upper_bound_ms:
            continue
        segment = audio[start_ms:end_ms]
        segment.export(os.path.join(target_dir, f"{file_name}-{i}.wav"), format="wav")
        total_time_ms += end_ms - start_ms

    return total_time_ms / 1000


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max_sec", "-M", type=int, default=15)
    parser.add_argument("--min_sec", "-m", type=int, default=2)
    parser.add_argument("--min_silence_dur_ms", "-s", type=int, default=700)
    args = parser.parse_args()

    input_dir = "/content/slice-and-transcribe/inputs"
    target_dir = "/content/slice-and-transcribe/raw"
    min_sec = args.min_sec
    max_sec = args.max_sec
    min_silence_dur_ms = args.min_silence_dur_ms

    wav_files = [
        os.path.join(input_dir, f)
        for f in os.listdir(input_dir)
        if f.lower().endswith(".wav")
    ]
    if os.path.exists(target_dir):  # ディレクトリを削除
        print(f"{target_dir}フォルダが存在するので、削除します。")
        shutil.rmtree(target_dir)

    total_sec = 0
    for wav_file in tqdm(wav_files):
        time_sec = split_wav(
            wav_file,
            target_dir,
            max_sec=max_sec,
            min_sec=min_sec,
            min_silence_dur_ms=min_silence_dur_ms,
        )
        total_sec += time_sec

    print(f"Done! Total time: {total_sec / 60:.2f} min.")
