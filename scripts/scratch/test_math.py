def calc(N, B_clusters, S_clusters, keep_frac):
    B_photos = N - S_clusters
    selected = B_clusters + int(S_clusters * keep_frac)
    return selected

print("Standard (0.55):", calc(1095, 173, 749, 0.55))
print("More (0.75):", calc(1095, 173, 749, 0.75))
print("If keep_frac = 1.0:", calc(1095, 173, 749, 1.0))
