# RAT Requirements Checklist

Source: "COMS3011A Test" spec — build a Repo Analysis Tool (RAT) web-app dashboard. Checkbox list of every requirement, including small ones. Rubric tiers are cumulative.

## Deliverable & submission

- [ ] 1. Build the "RAT" — a web-app dashboard that measures the specified metrics on a git repository.
- [ ] 2. Dashboard must handle **multiple repositories** (not a single-repo tool).
- [ ] 3. Submission is a URL to a **public** repository (commit everything, sane README, runnable instructions).
- [ ] 4. Features are cumulative/graded by rubric — not everything is strictly required to pass, but scope decisions must be driven by the rubric.

## Ingestion

- [ ] 5. Accept a repository as a **zip file** that contains the `.git` directory or file.
- [ ] 6. Accept a repository as a **remote URL**, which is then **deeply (fully) cloned** — full history, not shallow.
- [ ] 7. Both ingestion paths must produce an analysable repo (tier-graded: one form ≈ 50% tier, both ≈ 75% tier).

## Commit model & git semantics

- [ ] 8. Only **non-merge commits** are measured. \(\bar H\) = non-merge commits reachable from a reference commit \(h_r\) (typically HEAD).
- [ ] 9. Every commit \(h\) has: a single author \(h[a]\) (after author merging), a previous commit \(h[p]\), a committer date, a set of files \(h[F]\), a set of directories \(h[D]\).
- [ ] 10. The initial commit has \(h[p] = h_{\emptyset}\), the empty commit (so its whole file content counts as added lines).
- [ ] 11. Time filtering is keyed on **committer date**, not author date.
- [ ] 12. Objects (files/dirs) are identified by **path**.
- [ ] 13. **Rename detection is enabled at 50%** similarity threshold.
- [ ] 14. A pure rename must produce **zero change metrics** (rename alone changes nothing).
- [ ] 15. A change + rename must count **only the content changes**, attributed to the **new path**.
- [ ] 16. A deleted object (in \(h[p]\) but not \(h\)) must be recorded as a change (lines removed) **on its path** — deletion is not silently dropped.
- [ ] 17. **Binary files are not measured** (use git's own binary detection).

## Commit sets

- [ ] 18. A commit set \(H\) is an arbitrary subset of \(\bar H\).
- [ ] 19. \(H_t = \{h \in \bar H \mid t \le h[\text{committer-date}]\}\) — open-ended "from timestamp t to present".
- [ ] 20. \(H_{i,j} = \{h \in \bar H \mid i \le h[\text{committer-date}] < j\}\) — i inclusive, j exclusive.
- [ ] 21. Manually selected commit list = user-picked subset (not necessarily contiguous; no requirement that it be closed under ancestry).

## Object sets

- [ ] 22. \(H[F] = \bigcup_{h \in H} (h[F] \cup h[p][F])\) — **includes files that were deleted** (they appear via \(h[p]\)).
- [ ] 23. \(H[D] = \bigcup_{h \in H} (h[D] \cup h[p][D])\), **including the repository root**.

## Per-commit file metrics (the atomic inputs)

- [ ] 24. File Added Lines \(l^+_{h,f}\).
- [ ] 25. File Removed Lines \(l^-_{h,f}\).
- [ ] 26. File Growth \(\delta_{h,f} = l^+ - l^-\) (can be negative).
- [ ] 27. File Churn \(\lambda_{h,f} = l^+ + l^-\) (\(\ge 0\)).

## Per-commit directory metrics

- [ ] 28. Membership of a file/dir in directory \(d\) is via **immediate children**, but the sums recurse into subdirectories, so a directory's value is its **whole subtree total**.
- [ ] 29. Directory Added Lines \(l^+_{h,d}\), Directory Removed Lines \(l^-_{h,d}\).
- [ ] 30. Directory Growth \(\delta_{h,d}\), Directory Churn \(\lambda_{h,d}\).
- [ ] 31. **Repository metrics = directory metrics on the root** (no separate definition).

## Commit-set metrics (per object \(o \in H[F] \cup H[D]\))

- [ ] 32. Added lines \(l^+_{H,o} = \sum_{h \in H} l^+_{h,o}\); same pattern for \(l^-_{H,o}\), \(\delta_{H,o}\), \(\lambda_{H,o}\).
- [ ] 33. Modifications \(n_{H,o}\) = number of commits in \(H\) with \(\lambda_{h,o} > 0\) (indicator \(\mathbb{I}_n\)).
- [ ] 34. Modification frequency \(\eta_{H,o} = n_{H,o}/|H|\), and \(0\) when \(|H| = 0\).
- [ ] 35. Churn rate \(\rho_{H,o} = \lambda_{H,o}/|H|\), and \(0\) when \(|H| = 0\).

## Author metrics (per object \(o \in H[F] \cup H[D]\))

- [ ] 36. Authorship test \(\mathbb{I}(a,h) = 1\) iff \(a = h[a]\) (identity after merging).
- [ ] 37. Author modifications \(n_{H,o,a} = \sum_h \mathbb{I}(a,h)\cdot\mathbb{I}_n(h,o)\).
- [ ] 38. Author churn \(\lambda_{H,o,a} = \sum_h \lambda_{h,o}\cdot\mathbb{I}(a,h)\).
- [ ] 39. Author ownership \(\omega_{H,o,a} = \lambda_{H,o,a}/\lambda_{H,o}\), and \(0\) when \(\lambda_{H,o} = 0\). (The spec's PDF garbles this formula as "VW/VX" — it is a plain fraction.)
- [ ] 40. All commit-set and author metrics apply to **both files and directories** (including the root, via item 31).

## Filters & features

- [ ] 41. Filter by **repository**.
- [ ] 42. Filter by **author**.
- [ ] 43. Filter by **file or directory**.
- [ ] 44. Filter by **commit set** — specified period of time (supports both \(H_t\) and \(H_{i,j}\) forms).
- [ ] 45. Filter by **commit set** — manually selected list of commits.
- [ ] 46. **Author merging via `.mailmap`** (repo's mailmap file must be respected so different emails merge into one author).
- [ ] 47. **Manual author merging** when no mailmap is provided (and practically, always available as an override).
- [ ] 48. **Multi-repo support** in the dashboard.
- [ ] 49. Filters must combine (repo × author × object × commit set), not just work in isolation.

## Rubric quality bars

- [ ] 50. **25% tier:** some metric categories (repo, file, directory, set, author) implemented and *correct*.
- [ ] 51. **50% tier:** **all** metric categories implemented and correct + at least one ingestion method (zip or URL).
- [ ] 52. **75% tier:** both ingestion methods + at least one of {filtering, author merge, multi-repo}.
- [ ] 53. **100% tier:** all three of {filtering, author merge, multi-repo}.
- [ ] 54. **Architecture (25% of grade):** metric computation must be non-redundant and efficient; tiered from "redundant & slow" up to "efficient algorithms and architecture".
- [ ] 55. **Visualisation (inside Architecture 25%):** graded from "poor" up to "inspired"; strong charts for file/dir/author metrics are needed.
- [ ] 56. **Usability (25% of grade):** navigation quality, error handling, and QoL features; tiered from "poor navigation / no error handling / no QoL" up to "excellent".
- [ ] 57. **Performance tiers:** no slowness on small (~1,000 commits) repos; good performance on medium (~10,000 commits) by 75%; **good performance on large (~100,000 commits) repos for 100%** (i.e., git.git).
- [ ] 58. **Correctness validation:** metrics will be checked against **sample metrics from cJSON, Redis, and git at specific commit hashes** — build a validation harness and make sure you can compute metrics *as of an arbitrary commit hash*, not just HEAD.

---

Note: the rubric tier mapping in items 50–53 is a reconstruction from a garbled table in the spec (6 text fragments across 4 columns). Confirm with the lecturer before finalising scope.
