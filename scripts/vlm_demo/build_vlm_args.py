import json

d = json.load(open("data/tmp/vlm_demo_context.json", encoding="utf-8"))
out = []
for r in d:
    out.append({
        "video_id": r["video_id"], "niche": r["niche"], "perf_label": r["perf_label"],
        "perf_tercile": r["perf_tercile"], "duration_s": r["duration_s"],
        "caption": r["title_or_caption_opening"],
        "scalar_read": r["CURRENT_SYSTEM_OUTPUT"]["read"],
        "scalar_worth_trying": r["CURRENT_SYSTEM_OUTPUT"]["worth_trying"],
        "scalar_rec_card": r["CURRENT_SYSTEM_OUTPUT"]["rec_card"],
        "winner_openers": r["winner_context_for_this_cohort"]["winner_top_hook_openers"],
        "frame_abspath": "C:/Users/naadv/creative-director/" + r["frame_image"].replace("\\", "/"),
    })
json.dump(out, open("data/tmp/vlm_args.json", "w", encoding="utf-8"), ensure_ascii=False)
print("reels:", len(out))
