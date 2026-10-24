# Taipei Real-Photo Teaching Subset

29 unmodified 1280×720 serve JPEGs and the original complete 500-image COCO
`annotations/serve.json` are saved here under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

Credit: Wang, Chun-Yi; Lai, Kalin Guanlun; Huang, Hsu-Chun; Lin, Wei-Ting (2024).
*Tennis Player Actions Dataset for Human Pose Estimation*. Mendeley Data, V1.
[Original data and license](https://data.mendeley.com/datasets/nv3rpsxhhk/1),
[DOI](https://doi.org/10.17632/nv3rpsxhhk.1),
[primary paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC11282921/).

The original Mendeley browser page supplied license and checksum evidence.
Anonymous public downloads used the [Kaggle mirror](https://www.kaggle.com/datasets/orvile/tennis-player-actions-dataset).
The original S_001 JPEG and annotation-file hashes exactly matched the mirror.
[manifest.json](manifest.json) records every file's download URL, SHA-256,
version, credit and reuse terms; [kaggle_metadata.json](kaggle_metadata.json)
retains the public mirror license record. No account, API key or payment was used.

[serve-contact-sheet.jpg](serve-contact-sheet.jpg) is a resized montage, licensed
CC BY 4.0 with the same author credit. The original JPEGs are unchanged.
The dataset's `Serve` action label includes release, cocking, contact and
follow-through; it does not label every frame as Trophy Pose. Its 18 human
keypoints are 2D annotations, not measured 3D angle or coaching-correctness gold.

The repository's [photo benchmark](../photo-benchmark.json) adds visual phase/arm
inspection before inference. Eight clear preparation views, 19 other-stage views
and two uncertain views are distinguished; correctness/3D truth remain null.
S_160 (release/loading) and S_220 (uncertain cocking) are not forced into a phase.
The entire source remains one evaluation group. Clothing/court differences do
not establish independently identified players or recording sessions. This
subset was used to develop the focus feature; it is not unseen acceptance data.

To verify/recover these exact upstream files without a full dataset download:

```bash
.venv/bin/python docs/demo-assets/taipei/download_samples.py
```

The script skips matching files and verifies all 30 hashes. It downloads only
manifest-listed public assets. It is separate from the application's memory-only
upload path. Preserve the original author credit and indicate changes when
showing annotated/cropped derivatives.
