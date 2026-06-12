"""Temporary debug script to find gap frames near 82.5m."""
import re
import math
from pathlib import Path
from tracking_report_generator import (
    parse_frames,
    choose_track,
    build_event_ranges,
)

frames = parse_frames(
    Path("V02/Tracking_test-01-001/frame.txt").read_text(encoding="utf-8")
)
axis, selected = choose_track(frames, 1.0)

# Split into first cycle (distance reset > 20m marks new cycle)
cycle1 = []
for prev, cur in zip([None] + selected, selected):
    if prev is not None and cur.primary_distance_m - prev.primary_distance_m > 20.0:
        break
    cycle1.append(cur)

print("=== First cycle track samples near 82~83m ===")
print(f"{'FrameID':>10} {'Dist(m)':>9} {'Speed':>8} {'ObjID':>7}")
print("-" * 42)
for s in cycle1:
    if 81.0 <= s.primary_distance_m <= 84.0:
        print(f"{s.frame_id:>10} {s.primary_distance_m:>9.3f} {s.primary_speed_mps:>8.3f} {s.object_id:>7}")

print()
print("=== Gap events (frame_id discontinuity check) ===")
for prev, cur in zip(cycle1, cycle1[1:]):
    gap = cur.frame_id - prev.frame_id
    if gap > 1:
        print(
            f"  SKIP {gap-1} frame(s): "
            f"FrameID {prev.frame_id}({prev.primary_distance_m:.3f}m) "
            f"-> FrameID {cur.frame_id}({cur.primary_distance_m:.3f}m)"
        )

print()
print("=== Raw frames at the gap (82.4~82.8m) ===")
frame_index = {f.frame_id: f for f in frames}
for s in cycle1:
    if 82.3 <= s.primary_distance_m <= 82.8:
        prev_in_cycle = [x for x in cycle1 if x.frame_id < s.frame_id]
        if not prev_in_cycle:
            continue
        prev_s = prev_in_cycle[-1]
        gap = s.frame_id - prev_s.frame_id
        print(f"  prev FrameID={prev_s.frame_id} dist={prev_s.primary_distance_m:.3f}m")
        print(f"  curr FrameID={s.frame_id} dist={s.primary_distance_m:.3f}m  gap={gap}")

        # Show skipped frames
        for fid in range(prev_s.frame_id + 1, s.frame_id):
            f = frame_index.get(fid)
            if f:
                print(f"  [SKIPPED] FrameID={fid} objects={len(f.objects)} points={len(f.points)}")
                for obj in f.objects:
                    print(f"    ObjID={obj.object_id} DistLat={obj.dist_lat_m:.3f} DistLong={obj.dist_long_m:.3f} VreLat={obj.vre_lat_mps:.3f} VreLong={obj.vre_long_mps:.3f}")
            else:
                print(f"  [SKIPPED] FrameID={fid} (not found in file)")
        print()
