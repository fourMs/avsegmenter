"""Who is speaking when: VAD + speaker embeddings + clustering, for talk-heavy recordings.

A defence, a seminar or a panel is one long speech segment to a sound-event tagger. What the
viewer wants is the *turns*: who spoke, when, for how long. This module cuts the speech into
short windows (silero VAD), embeds each with an ECAPA-TDNN speaker encoder (speechbrain), clusters
the embeddings (agglomerative, cosine) and smooths the labels into turns. Speakers come out as
``S0, S1, ...`` ordered by total speaking time; roles are suggested from where and how much
each one speaks, and a user file can name them.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np

SR = 16000
WIN_S, HOP_S = 1.5, 0.75


def speech_regions(y16: np.ndarray, log=print) -> list[tuple[float, float]]:
    """silero-VAD speech spans in seconds."""
    import torch
    from silero_vad import load_silero_vad, get_speech_timestamps
    model = load_silero_vad()
    ts = get_speech_timestamps(torch.from_numpy(np.ascontiguousarray(np.asarray(y16, dtype=np.float32))), model,
                               sampling_rate=SR, min_speech_duration_ms=300, min_silence_duration_ms=400, return_seconds=True)
    return [(float(t["start"]), float(t["end"])) for t in ts]


def embed_windows(y16: np.ndarray, regions: list[tuple[float, float]], device: str = "cuda", log=print) -> tuple[np.ndarray, np.ndarray]:
    """(times, embeddings) for WIN_S windows every HOP_S inside the speech regions."""
    import torch
    from speechbrain.inference.speaker import EncoderClassifier
    enc = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb",
                                         savedir=str(Path.home() / ".cache/speechbrain/spkrec-ecapa-voxceleb"),
                                         run_opts={"device": device})
    starts = []
    for a, b in regions:
        t = a
        while t + WIN_S <= b + 0.3:
            starts.append(t); t += HOP_S
        if not starts or starts[-1] < a:          # a region shorter than one window still gets one
            starts.append(a)
    starts = np.array(sorted(set(starts)))
    win = int(WIN_S * SR)
    embs = np.zeros((len(starts), 192), np.float32)
    B = 64
    with torch.no_grad():
        for i in range(0, len(starts), B):
            batch = np.zeros((min(B, len(starts) - i), win), np.float32)
            for k, s in enumerate(starts[i:i + B]):
                a = int(s * SR); seg = np.asarray(y16[a:a + win], dtype=np.float32)
                batch[k, :len(seg)] = seg
            e = enc.encode_batch(torch.from_numpy(batch).to(device)).squeeze(1).cpu().numpy()
            embs[i:i + len(e)] = e / (np.linalg.norm(e, axis=1, keepdims=True) + 1e-9)
            if (i // B) % 50 == 0:
                log(f"  embeddings {i}/{len(starts)}")
    return starts + WIN_S / 2, embs


def prepare(embs: np.ndarray, center: bool = True) -> np.ndarray:
    """Session-centred, unit-length embeddings: removing the room/microphone mean sharpens the speaker directions."""
    X = np.asarray(embs, np.float32)
    if center and len(X) > 1:
        X = X - X.mean(axis=0)
    return X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)


def cluster(embs: np.ndarray, threshold: float = 0.75, n_speakers: int | None = None, min_cluster_s: float = 60.0,
            hop_s: float = HOP_S) -> np.ndarray:
    """Agglomerative clustering on cosine distance (average linkage). ``threshold`` is the merge distance when the
    number of speakers is unknown; clusters with less than ``min_cluster_s`` of speech are folded into the nearest
    large cluster's centroid, so a cough or a distant question does not become a speaker of its own."""
    from sklearn.cluster import AgglomerativeClustering
    if len(embs) < 2:
        return np.zeros(len(embs), int)
    if n_speakers:
        ac = AgglomerativeClustering(n_clusters=n_speakers, metric="cosine", linkage="average")
    else:
        ac = AgglomerativeClustering(n_clusters=None, distance_threshold=threshold, metric="cosine", linkage="average")
    lab = ac.fit_predict(embs)
    uniq, counts = np.unique(lab, return_counts=True)
    big = [u for u, c in zip(uniq, counts) if c * hop_s >= min_cluster_s]
    if not big:
        big = [uniq[counts.argmax()]]
    if len(big) < len(uniq):
        cents = np.stack([embs[lab == u].mean(axis=0) for u in big])
        cents /= np.linalg.norm(cents, axis=1, keepdims=True) + 1e-9
        small = ~np.isin(lab, big)
        lab = lab.copy()
        lab[small] = np.array(big)[(embs[small] @ cents.T).argmax(axis=1)]
    return lab


def smooth_labels(times: np.ndarray, labels: np.ndarray, width: int = 5) -> np.ndarray:
    """Majority vote over neighbouring windows, but only within the same contiguous speech run."""
    out = labels.copy()
    h = width // 2
    for i in range(len(labels)):
        lo, hi = i, i
        while lo > 0 and i - lo < h and times[lo] - times[lo - 1] <= HOP_S * 1.5:
            lo -= 1
        while hi < len(labels) - 1 and hi - i < h and times[hi + 1] - times[hi] <= HOP_S * 1.5:
            hi += 1
        vals, counts = np.unique(labels[lo:hi + 1], return_counts=True)
        out[i] = vals[counts.argmax()] if counts.max() > (hi - lo + 1) / 2 else labels[i]
    return out


def turns_from_labels(times: np.ndarray, labels: np.ndarray, min_turn_s: float = 2.0) -> list[dict]:
    """Merge consecutive windows of one speaker into turns; drop turns shorter than ``min_turn_s`` into neighbours."""
    turns = []
    for t, l in zip(times, labels):
        a, b = t - WIN_S / 2, t + WIN_S / 2
        if turns and turns[-1]["label"] == int(l) and a - turns[-1]["end"] <= HOP_S * 1.5:
            turns[-1]["end"] = b
        else:
            turns.append({"label": int(l), "start": a, "end": b})
    changed = True
    while changed and len(turns) > 1:
        changed = False
        for k, t in enumerate(turns):
            if t["end"] - t["start"] >= min_turn_s:
                continue
            prev = turns[k - 1] if k > 0 else None
            nxt = turns[k + 1] if k + 1 < len(turns) else None
            if prev is not None and (nxt is None or prev["end"] >= t["start"] - HOP_S * 1.5):
                prev["end"] = max(prev["end"], t["end"])
            elif nxt is not None:
                nxt["start"] = min(nxt["start"], t["start"])
            else:
                continue
            del turns[k]; changed = True
            break
    # merge same-speaker neighbours again after absorption
    merged = []
    for t in turns:
        if merged and merged[-1]["label"] == t["label"] and t["start"] - merged[-1]["end"] <= HOP_S * 1.5:
            merged[-1]["end"] = t["end"]
        else:
            merged.append(dict(t))
    return merged


def rename_by_time(turns: list[dict]) -> tuple[list[dict], dict]:
    """Relabel clusters S0, S1, ... by total speaking time (most first)."""
    total = {}
    for t in turns:
        total[t["label"]] = total.get(t["label"], 0.0) + t["end"] - t["start"]
    order = sorted(total, key=lambda k: -total[k])
    names = {old: f"S{i}" for i, old in enumerate(order)}
    for t in turns:
        t["speaker"] = names[t["label"]]; del t["label"]
    stats = {names[k]: {"total_s": round(v, 1), "first_at": min(t["start"] for t in turns if t["speaker"] == names[k]),
                        "turns": sum(1 for t in turns if t["speaker"] == names[k])} for k, v in total.items()}
    return turns, stats


def suggest_roles(stats: dict, parts: list[dict] | None = None) -> dict:
    """Heuristic roles from where and how much each voice speaks: the voice heard first is the host or chair,
    the voice with the most speaking time the main speaker, further voices with minutes of talk are
    speakers 1, 2, …, the rest brief voices (questions, announcements). A suggestion to be replaced by names
    in curated.json; in a defence the main speaker is the candidate and the numbered speakers the opponents."""
    if not stats:
        return {}
    by_time = sorted(stats, key=lambda s: -stats[s]["total_s"])
    by_first = sorted(stats, key=lambda s: stats[s]["first_at"])
    roles = {}
    roles[by_time[0]] = "main speaker"
    chair = by_first[0] if by_first[0] != by_time[0] else (by_first[1] if len(by_first) > 1 else None)
    if chair:
        roles[chair] = "host / chair"
    n = 1
    for s in by_time[1:]:
        if s in roles:
            continue
        if stats[s]["total_s"] >= 300:
            roles[s] = f"speaker {n}"; n += 1
        else:
            roles[s] = "brief voice"
    return roles


def diarize(y16: np.ndarray, out_dir: Path, device: str = "cuda", threshold: float = 0.75,
            n_speakers: int | None = None, center: bool = False, log=print) -> dict:
    """Whole chain, cached as speakers.json (embeddings cached separately, so re-clustering is instant):
    {"turns": [...], "speakers": {S0: stats}, "roles": {...}}."""
    cache = out_dir / "speakers.json"
    if cache.exists():
        return json.loads(cache.read_text())
    emb_cache = out_dir / "speaker_embeddings.npz"
    if emb_cache.exists():
        z = np.load(emb_cache); times, embs = z["times"], z["embs"]
        regions = [tuple(r) for r in z["regions"]] if "regions" in z else []
    else:
        regions = speech_regions(y16, log)
        log(f"  VAD: {len(regions)} speech regions, {sum(b - a for a, b in regions) / 60:.0f} min of speech")
        times, embs = embed_windows(y16, regions, device, log)
        np.savez(emb_cache, times=times, embs=embs, regions=np.array(regions, dtype=float).reshape(-1, 2))
    labels = smooth_labels(times, cluster(prepare(embs, center), threshold, n_speakers))
    turns, stats = rename_by_time(turns_from_labels(times, labels))
    for t in turns:
        t["start"] = round(t["start"], 2); t["end"] = round(t["end"], 2)
    out = {"turns": turns, "speakers": stats, "roles": suggest_roles(stats), "threshold": threshold, "centered": center,
           "n_speakers": len(stats), "speech_regions": [[round(float(a), 2), round(float(b), 2)] for a, b in regions]}
    cache.write_text(json.dumps(out))
    return out


def speaker_of(turns: list[dict], start: float, end: float) -> dict:
    """Speaking-time share per speaker inside a span."""
    share = {}
    for t in turns:
        ov = min(end, t["end"]) - max(start, t["start"])
        if ov > 0:
            share[t["speaker"]] = share.get(t["speaker"], 0.0) + ov
    tot = sum(share.values()) or 1.0
    return {k: round(v / tot, 3) for k, v in sorted(share.items(), key=lambda kv: -kv[1])}
