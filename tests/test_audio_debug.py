import struct

from wyndle.audio.debug import measure_pcm


def test_measure_pcm_reports_requested_fields():
    pcm = struct.pack("<5h", 0, 0, -100, 50, 100)
    metrics = measure_pcm(pcm)
    assert metrics.sample_count == 5
    assert metrics.peak == 100
    assert metrics.minimum == -100
    assert metrics.maximum == 100
    assert metrics.unique_samples == 4
    assert metrics.zero_percent == 40.0
    assert metrics.rms > 0
