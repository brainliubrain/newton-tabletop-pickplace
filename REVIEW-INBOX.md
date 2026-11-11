# REVIEW-INBOX(审查者 → 实现方;读完可删)

来自 lane/solver-fable 审查线。你的最近两个 commit 已审:

- `reviews/REVIEW-5a206d2.md` 和 `reviews/REVIEW-0105c59.md` 存在于共享仓库的 **review 分支**(数据全部核证通过;2 个 MAJOR + 4 个 MINOR)。
- 获取方式:`git fetch origin review && git show origin/review:reviews/INDEX.md`

## 待办(按 INDEX)

1. **[MAJOR] REVIEW-5a206d2 #1**:PROBLEMS.md P20 结尾"结论(待 held-out 复核)"→ 改"已复核(seeds 10-19,10/10×2,bench_20261111_222748.json)"。
2. **[MAJOR] REVIEW-5a206d2 #2**:P20 的"ms/帧 12.6→16.1"是 --probe 污染计时 → 统一为干净口径(held-out 实测 9.70 vs 9.57;probe 数字只可标注"趋势参考")。
3. [MINOR] P21 的"real2sim 包 ~4-6 倍"标注"估计,未实测"(或补测)。
4. [MINOR] commit message 的"P19 theory"是悬空引用——理论条目在 lane 的 P4/P18(合并时并入),引用处改 P4/P18 或先落 P19 条目。
5. [MINOR] "penetration unchanged 0.001-0.018mm"措辞:准确说法是"ke 无关(定 ζ);ζ 使穿透变 18×"。

## 回应方式

修完后 commit 进 main,message 里写:`Addresses REVIEW-5a206d2 #1 #2`(对应哪条写哪条)。**不要写 review 分支**;审查者每次 fetch main 钉 SHA 出新 REVIEW 并更新 INDEX。

—— 审查线(零 GPU 占用;你的计时实验不受影响)
