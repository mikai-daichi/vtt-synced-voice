"""手動テスト用スクリプト。
vtt_synced_voice パッケージの動作確認に使用する。
"""
from vtt_synced_voice import transcribe

transcribe(
    audio_file="audio_input/test_audio.m4a",
    output_file="vtt_output/test_package.vtt",
    language="ja",
    model="large-v2",
    device="cpu",
    margin_before=0.066,
    margin_after=0.0,
    silence_threshold=0.001,
    verbose=True,
    dry_run=False,
)
