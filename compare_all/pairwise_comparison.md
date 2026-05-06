# Pairwise A/B Statistical Comparison (Top 4 by F1)

Top 4 experiments: claude-code-sonnet, pentagi-sonnet, pentagi-gpt, strix-sonnet

Statistical tests use per-run overall (unweighted) scores (n=3 per experiment).


| | F1 | F0.5 | Recall | Precision |
|---|---|---|---|---|
| **claude-code-sonnet vs strix-sonnet** | | | | |
| Difference | +16.79% | +7.54% | +18.83% | -14.19% |
| p-value | 0.0141 | 0.1501 | 0.0047 | 0.0445 |
| Cohen's d | 3.504 | 1.452 | 4.981 | -3.050 |
| **claude-code-sonnet vs pentagi-gpt** | | | | |
| Difference | +14.49% | +9.53% | +15.43% | -0.77% |
| p-value | 0.0110 | 0.0671 | 0.0043 | 0.8928 |
| Cohen's d | 3.746 | 2.132 | 4.778 | -0.117 |
| **pentagi-sonnet vs strix-sonnet** | | | | |
| Difference | +12.35% | -0.29% | +17.28% | -25.70% |
| p-value | 0.0577 | 0.9577 | 0.0116 | 0.0276 |
| Cohen's d | 2.168 | -0.046 | 3.673 | -4.147 |
| **pentagi-sonnet vs pentagi-gpt** | | | | |
| Difference | +10.05% | +1.70% | +13.89% | -12.28% |
| p-value | 0.0835 | 0.7383 | 0.0225 | 0.1261 |
| Cohen's d | 2.033 | 0.300 | 3.248 | -1.591 |
| **claude-code-sonnet vs pentagi-sonnet** | | | | |
| Difference | +4.44% | +7.83% | +1.54% | +11.51% |
| p-value | 0.3633 | 0.2081 | 0.6843 | 0.1365 |
| Cohen's d | 0.850 | 1.247 | 0.362 | 1.553 |
| **pentagi-gpt vs strix-sonnet** | | | | |
| Difference | +2.30% | -1.99% | +3.40% | -13.43% |
| p-value | 0.5691 | 0.6157 | 0.3393 | 0.0657 |
| Cohen's d | 0.513 | -0.448 | 0.894 | -2.617 |

*Note: With n=3 per experiment, statistical power is limited. Interpret p-values cautiously.*
