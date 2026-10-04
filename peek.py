import glob, collections
f = glob.glob(r"validation/data/2020-05-14-US-MTV-2/*_GnssLog.txt")[0]
seen, count = {}, collections.Counter()
for line in open(f, errors="ignore"):
    k = line.split(",")[0].strip()
    count[k] += 1
    if k not in seen:
        seen[k] = line.strip()[:200]
for k, v in seen.items():
    print(count[k], "|", v)