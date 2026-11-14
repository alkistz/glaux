"""CPU benchmark of multilingual embedding models on Diavgeia-style Greek text.

Quality: 25 queries against 44 hand-written decision subjects (synthetic, not real decisions).
Speed: subjects (short) and ~1200-character chunks, fp32 and bf16. Results: docs/log.md.

Needs torch and sentence-transformers, which are not project dependencies. Run in a separate venv:
    uv venv /tmp/embbench && uv pip install --python /tmp/embbench/bin/python \
        --index-url https://download.pytorch.org/whl/cpu torch && \
        uv pip install --python /tmp/embbench/bin/python sentence-transformers
    /tmp/embbench/bin/python scripts/bench_embeddings.py [model-name-filter ...]
"""

import json
import sys
import time
import unicodedata

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

SUBJECTS = [
    "Προμήθεια καυσίμου κίνησης και θέρμανσης για τις ανάγκες του Δήμου έτους 2026",  # 0
    "Προμήθεια ελαστικών για τα οχήματα και τα μηχανήματα έργου του Δήμου",  # 1
    "Ανάθεση υπηρεσίας καθαρισμού σχολικών μονάδων πρωτοβάθμιας εκπαίδευσης",  # 2
    "Προμήθεια ειδών καθαριότητας και ευπρεπισμού για τις υπηρεσίες του Δήμου",  # 3
    "Προμήθεια γραφικής ύλης και φωτοαντιγραφικού χαρτιού",  # 4
    "Προμήθεια μελανιών και τόνερ για τους εκτυπωτές των υπηρεσιών",  # 5
    "Έγκριση δαπάνης και διάθεση πίστωσης για την αμοιβή νομικού παραστάτη του Δήμου",  # 6
    "Ανάθεση σύνταξης γνωμοδότησης σε δικηγόρο για υπόθεση απαλλοτρίωσης",  # 7
    "Συντήρηση και επισκευή μεταφορικών μέσων του Δήμου",  # 8
    "Προμήθεια ανταλλακτικών για την επισκευή απορριμματοφόρων",  # 9
    "Προμήθεια λαμπτήρων LED για τον οδοφωτισμό",  # 10
    "Συντήρηση εγκαταστάσεων ηλεκτροφωτισμού κοινόχρηστων χώρων",  # 11
    "Μίσθωση μηχανημάτων έργου για τον αποχιονισμό του οδικού δικτύου",  # 12
    "Προμήθεια αλατιού για την αντιμετώπιση του παγετού",  # 13
    "Καθαρισμός οικοπέδων και κοινόχρηστων χώρων από ξερά χόρτα για την πρόληψη πυρκαγιών",  # 14
    "Προμήθεια εμφιαλωμένου νερού για τις ανάγκες των εργαζομένων",  # 15
    "Προμήθεια υδρομετρητών για το δίκτυο ύδρευσης",  # 16
    "Αποκατάσταση βλαβών στο δίκτυο ύδρευσης της Δημοτικής Κοινότητας",  # 17
    "Παροχή υπηρεσιών σίτισης μαθητών στα σχολεία του Δήμου",  # 18
    "Προμήθεια τροφίμων για τους παιδικούς σταθμούς",  # 19
    "Ανάπλαση και προμήθεια εξοπλισμού χώρων παιχνιδιού",  # 20
    "Ασφάλιση μεταφορικών μέσων και μηχανημάτων του Δήμου για το έτος 2026",  # 21
    "Έγκριση δαπάνης για τις εορταστικές εκδηλώσεις Χριστουγέννων και Πρωτοχρονιάς",  # 22
    "Διοργάνωση πολιτιστικών εκδηλώσεων θερινής περιόδου",  # 23
    "Εκπόνηση μελέτης για την ενεργειακή αναβάθμιση του δημαρχιακού μεγάρου",  # 24
    "Ασφαλτόστρωση και βελτίωση αγροτικής οδοποιίας",  # 25
    "Αποκατάσταση φθορών οδοστρώματος με εργασίες συντήρησης",  # 26
    "Προμήθεια και τοποθέτηση κάδων απορριμμάτων",  # 27
    "Μεταφορά και διάθεση αστικών στερεών αποβλήτων στον ΧΥΤΑ",  # 28
    "Απολύμανση, μυοκτονία και απεντόμωση δημοτικών κτιρίων",  # 29
    "Προμήθεια ιατροφαρμακευτικού υλικού για το Κέντρο Υγείας",  # 30
    "Προμήθεια ηλεκτρονικών υπολογιστών και περιφερειακών συσκευών",  # 31
    "Ανάθεση υπηρεσιών υποστήριξης και φιλοξενίας της ιστοσελίδας του Δήμου",  # 32
    "Συντήρηση ανελκυστήρων δημοτικών κτιρίων",  # 33
    "Συντήρηση και επισκευή κλιματιστικών μονάδων",  # 34
    "Έγκριση δαπάνης για τη συνδρομή σε νομικές βάσεις δεδομένων",  # 35
    "Προμήθεια στολών και ειδών ατομικής προστασίας για το προσωπικό",  # 36
    "Περισυλλογή και φιλοξενία αδέσποτων ζώων συντροφιάς",  # 37
    "Δαπάνη για την ταχυδρόμηση της αλληλογραφίας του Δήμου",  # 38
    "Πληρωμή λογαριασμών ηλεκτρικής ενέργειας δημοτικών κτιρίων",  # 39
    "Μίσθωση ακινήτου για τη στέγαση του ΚΕΠ",  # 40
    "Προμήθεια φυτών και λιπασμάτων για τους χώρους πρασίνου",  # 41
    "Κλάδεμα και κοπή επικίνδυνων δέντρων",  # 42
    "Μεταφορά μαθητών με μισθωμένα λεωφορεία για το σχολικό έτος",  # 43
]

# (query, relevant subject ids, kind)
QUERIES = [
    ("προμήθεια καυσίμων", {0}, "inflection"),
    ("πετρέλαιο για τα αυτοκίνητα του δήμου", {0}, "concept"),
    ("καθαρισμος σχολειων", {2}, "no accents"),
    ("αγορά χαρτικών", {4}, "synonym"),
    ("αμοιβή δικηγόρου", {6, 7}, "synonym"),
    ("επισκευή αυτοκινήτων", {8, 9}, "synonym"),
    ("φωτισμός δρόμων", {10, 11}, "synonym"),
    ("χιόνια και παγετός στους δρόμους", {12, 13}, "concept"),
    ("πυροπροστασία", {14}, "concept"),
    ("νερό για τους υπαλλήλους", {15}, "hard negative"),
    ("βλάβη στην ύδρευση", {17}, "inflection"),
    ("school meals", {18}, "english"),
    ("παιδικές χαρές", {20}, "concept"),
    ("ασφαλιστήριο για τα οχήματα", {21}, "synonym"),
    ("γιορτές Χριστουγέννων", {22}, "synonym"),
    ("λακκούβες στο δρόμο", {25, 26}, "colloquial"),
    ("σκουπίδια", {27, 28}, "colloquial"),
    ("ποντίκια και κατσαρίδες", {29}, "colloquial"),
    ("υπολογιστές", {31}, "inflection"),
    ("κλιματισμός", {34}, "inflection"),
    ("promitheia kafsimon", {0}, "greeklish"),
    ("αδέσποτα σκυλιά", {37}, "colloquial"),
    ("ρεύμα κτιρίων", {39}, "colloquial"),
    ("ενοίκιο για γραφεία", {40}, "concept"),
    ("μεταφορά μαθητών", {43}, "exact"),
]

CHUNK_SOURCE = (
    "Έχοντας υπόψη: 1. Τις διατάξεις του άρθρου 58 του Ν. 3852/2010 για τη νέα αρχιτεκτονική "
    "της αυτοδιοίκησης και της αποκεντρωμένης διοίκησης, όπως ισχύει. 2. Τις διατάξεις του Ν. "
    "4412/2016 για τις δημόσιες συμβάσεις έργων, προμηθειών και υπηρεσιών, και ειδικότερα του "
    "άρθρου 118 περί απευθείας ανάθεσης. 3. Τις διατάξεις του Π.Δ. 80/2016 για την ανάληψη "
    "υποχρεώσεων από τους διατάκτες. 4. Την υπ' αριθμ. 245/2025 απόφαση της Οικονομικής "
    "Επιτροπής για την έγκριση του προϋπολογισμού οικονομικού έτους 2026. 5. Την ανάγκη "
    "προμήθειας των ειδών για την εύρυθμη λειτουργία των υπηρεσιών του Δήμου. 6. Την "
    "προσφορά του οικονομικού φορέα, η οποία κρίνεται συμφέρουσα για τον Δήμο. 7. Το γεγονός "
    "ότι υπάρχει εγγεγραμμένη πίστωση στον Κ.Α. 10.6615.0001 του προϋπολογισμού. Αποφασίζουμε: "
    "Αναθέτουμε απευθείας την προμήθεια των ειδών, συνολικής δαπάνης 18.600,00 ευρώ "
    "συμπεριλαμβανομένου του ΦΠΑ 24%, σύμφωνα με την τεχνική έκθεση της υπηρεσίας. Ο ανάδοχος "
    "υποχρεούται να παραδώσει τα είδη εντός τριάντα ημερών από την υπογραφή της σύμβασης. Η "
    "πληρωμή θα γίνει με την προσκόμιση των νόμιμων δικαιολογητικών και του τιμολογίου. "
)


def norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.casefold().replace("ς", "σ")


def tokens(text: str) -> list[str]:
    out, word = [], []
    for c in norm(text):
        if c.isalnum():
            word.append(c)
        elif word:
            out.append("".join(word))
            word = []
    if word:
        out.append("".join(word))
    return out


def lexical_rank(query: str, prefix: int | None) -> list[int]:
    """AND semantics like websearch_to_tsquery with config simple; optional prefix match."""
    q = tokens(query)
    hits = []
    for i, s in enumerate(SUBJECTS):
        doc = tokens(s)
        if prefix:
            ok = all(any(d.startswith(t[:prefix]) for d in doc) for t in q)
        else:
            ok = all(t in doc for t in q)
        if ok:
            hits.append(i)
    return hits


def metrics(rankings: list[list[int]]) -> dict:
    h1 = h3 = rr = 0.0
    per = []
    for ranking, (_, rel, _) in zip(rankings, QUERIES, strict=True):
        first = next((r for r, i in enumerate(ranking, 1) if i in rel), None)
        per.append(first)
        if first == 1:
            h1 += 1
        if first and first <= 3:
            h3 += 1
        if first:
            rr += 1 / first
    n = len(QUERIES)
    return {"hit@1": h1 / n, "hit@3": h3 / n, "mrr": rr / n, "first_relevant_rank": per}


def make_chunks(n: int, size: int = 1200) -> list[str]:
    sentences = CHUNK_SOURCE.split(". ")
    out = []
    for i in range(n):
        rot = sentences[i % len(sentences) :] + sentences[: i % len(sentences)]
        text = ". ".join(rot) * 2
        out.append(f"Απόφαση {i}. " + text[:size])
    return out


def throughput(model, texts, batch_size, prefix=""):
    texts = [prefix + t for t in texts]
    model.encode(texts[:batch_size], batch_size=batch_size)  # warm-up
    t0 = time.perf_counter()
    emb = model.encode(texts, batch_size=batch_size, normalize_embeddings=True)
    dt = time.perf_counter() - t0
    return len(texts) / dt, emb


MODELS = {
    "mpnet-base-v2 (278M, cached)": {
        "id": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        "q": "",
        "d": "",
    },
    "multilingual-e5-small (118M)": {
        "id": "intfloat/multilingual-e5-small",
        "q": "query: ",
        "d": "passage: ",
    },
    "bge-m3 (568M)": {"id": "BAAI/bge-m3", "q": "", "d": ""},
    "qwen3-embedding-0.6B (596M)": {
        "id": "Qwen/Qwen3-Embedding-0.6B",
        "q": "Instruct: Given a search query about Greek public spending, retrieve the matching "
        "decision subject\nQuery:",
        "d": "",
    },
}


def main():
    only = sys.argv[1:]
    results = {}
    for name in ("simple FTS, exact", "simple FTS, 5-char prefix"):
        prefix = 5 if "prefix" in name else None
        results[name] = metrics([lexical_rank(q, prefix) for q, _, _ in QUERIES])
        print(
            name, {k: v for k, v in results[name].items() if k != "first_relevant_rank"}, flush=True
        )

    subjects_big = [f"{s} (αρ. {i})" for i in range(25) for s in SUBJECTS][:1000]
    chunks = make_chunks(192)

    for name, cfg in MODELS.items():
        if only and not any(o in name for o in only):
            continue
        t0 = time.perf_counter()
        model = SentenceTransformer(cfg["id"], device="cpu")
        load_s = time.perf_counter() - t0
        model.max_seq_length = 512
        tok = model.tokenizer
        chunk_tokens = int(np.median([len(tok(c)["input_ids"]) for c in chunks[:20]]))
        subj_tokens = int(np.median([len(tok(s)["input_ids"]) for s in SUBJECTS]))

        # quality
        d = model.encode([cfg["d"] + s for s in SUBJECTS], normalize_embeddings=True)
        q = model.encode([cfg["q"] + x for x, _, _ in QUERIES], normalize_embeddings=True)
        sims = q @ d.T
        rankings = [list(np.argsort(-row)) for row in sims]
        res = metrics(rankings)
        res["top1"] = [int(r[0]) for r in rankings]

        # speed, fp32
        res["load_s"] = round(load_s, 1)
        res["subject_tokens_median"] = subj_tokens
        res["chunk_tokens_median"] = chunk_tokens
        res["subjects_per_s_fp32"], _ = throughput(model, subjects_big, 64, cfg["d"])
        res["chunks_per_s_fp32"], emb32 = throughput(model, chunks, 16, cfg["d"])

        # speed, bf16 (Zen 5 has AVX-512 BF16)
        model = model.to(torch.bfloat16)
        res["subjects_per_s_bf16"], _ = throughput(model, subjects_big, 64, cfg["d"])
        res["chunks_per_s_bf16"], emb16 = throughput(model, chunks, 16, cfg["d"])
        res["bf16_vs_fp32_cosine_min"] = float(
            np.min(np.sum(emb32 * emb16.astype(np.float32), axis=1))
        )

        results[name] = res
        show = {
            k: (round(v, 3) if isinstance(v, float) else v)
            for k, v in res.items()
            if k not in ("first_relevant_rank", "top1")
        }
        print(name, show, flush=True)
        del model

    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(
            {"queries": [[q, sorted(r), k] for q, r, k in QUERIES], "results": results},
            f,
            ensure_ascii=False,
            indent=1,
            default=float,
        )


if __name__ == "__main__":
    main()
