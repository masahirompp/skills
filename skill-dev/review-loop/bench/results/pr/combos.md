## 構成の組み合わせ(1反復あたり。不具合は 41 件、題材は 10 件)

| 組み合わせ | 検出した不具合(試行ごと) | 平均 | 本物でない余計な指摘 / 題材 | 本物の余計な指摘 / 題材 | 時間 / 題材 | 費用 / 題材 |
|---|---|---|---|---|---|---|
| code-review | 21 | 21.0(51%) | 5.2 | 0.7 | 2.6分 | $0.61 |
| perspectives | 16 | 16.0(39%) | 5.7 | 0.7 | 2.0分 | $0.63 |
| mattpocock | 9 | 9.0(22%) | 8.1 | 0.1 | 3.4分 | $1.08 |
| prove | 5 | 5.0(12%) | 0.0 | 0.1 | 4.1分 | $0.68 |
| security-review | 2 | 2.0(5%) | 0.0 | 0.0 | 0.7分 | $0.40 |
| code-review + mattpocock | 22 | 22.0(54%) | 11.5 | 0.7 | 3.8分 | $1.69 |
| code-review + perspectives | 22 | 22.0(54%) | 9.5 | 1.2 | 2.7分 | $1.23 |
| code-review + prove | 22 | 22.0(54%) | 5.2 | 0.7 | 4.2分 | $1.29 |
| code-review + security-review | 21 | 21.0(51%) | 5.2 | 0.7 | 2.6分 | $1.01 |
| mattpocock + perspectives | 17 | 17.0(41%) | 13.3 | 0.7 | 3.5分 | $1.71 |
| perspectives + prove | 17 | 17.0(41%) | 5.7 | 0.7 | 4.3分 | $1.31 |
| security-review + perspectives | 16 | 16.0(39%) | 5.7 | 0.7 | 2.0分 | $1.03 |
| security-review + mattpocock | 11 | 11.0(27%) | 8.1 | 0.1 | 3.4分 | $1.48 |
| mattpocock + prove | 10 | 10.0(24%) | 8.1 | 0.1 | 4.6分 | $1.77 |
| security-review + prove | 7 | 7.0(17%) | 0.0 | 0.1 | 4.1分 | $1.08 |
| code-review + mattpocock + perspectives | 23 | 23.0(56%) | 15.7 | 1.2 | 3.8分 | $2.32 |
| code-review + mattpocock + prove | 23 | 23.0(56%) | 11.5 | 0.7 | 4.6分 | $2.37 |
| code-review + perspectives + prove | 23 | 23.0(56%) | 9.5 | 1.2 | 4.3分 | $1.92 |
| code-review + security-review + mattpocock | 22 | 22.0(54%) | 11.5 | 0.7 | 3.8分 | $2.09 |
| code-review + security-review + perspectives | 22 | 22.0(54%) | 9.5 | 1.2 | 2.7分 | $1.63 |
| code-review + security-review + prove | 22 | 22.0(54%) | 5.2 | 0.7 | 4.2分 | $1.69 |
| mattpocock + perspectives + prove | 18 | 18.0(44%) | 13.3 | 0.7 | 4.7分 | $2.39 |
| security-review + mattpocock + perspectives | 17 | 17.0(41%) | 13.3 | 0.7 | 3.5分 | $2.11 |
| security-review + perspectives + prove | 17 | 17.0(41%) | 5.7 | 0.7 | 4.3分 | $1.71 |
| security-review + mattpocock + prove | 12 | 12.0(29%) | 8.1 | 0.1 | 4.6分 | $2.17 |
| code-review + mattpocock + perspectives + prove | 24 | 24.0(59%) | 15.7 | 1.2 | 4.7分 | $3.00 |
| code-review + security-review + mattpocock + perspectives | 23 | 23.0(56%) | 15.7 | 1.2 | 3.8分 | $2.72 |
| code-review + security-review + mattpocock + prove | 23 | 23.0(56%) | 11.5 | 0.7 | 4.6分 | $2.77 |
| code-review + security-review + perspectives + prove | 23 | 23.0(56%) | 9.5 | 1.2 | 4.3分 | $2.32 |
| security-review + mattpocock + perspectives + prove | 18 | 18.0(44%) | 13.3 | 0.7 | 4.7分 | $2.79 |
| code-review + security-review + mattpocock + perspectives + prove | 24 | 24.0(59%) | 15.7 | 1.2 | 4.7分 | $3.40 |

## 構成どうしの検出率の差(不具合を単位にしたブートストラップ、95% の幅)

| 比べる構成 | 差(ポイント) | 95% の幅 | 0 をまたぐか |
|---|---|---|---|
| code-review − security-review | +46 | +32 〜 +61 | またがない |
| code-review − mattpocock | +29 | +15 〜 +46 | またがない |
| code-review − perspectives | +12 | +0 〜 +24 | またぐ(差があるとは言えない) |
| code-review − prove | +39 | +24 〜 +56 | またがない |
| security-review − mattpocock | -17 | -32 〜 -2 | またがない |
| security-review − perspectives | -34 | -49 〜 -20 | またがない |
| security-review − prove | -7 | -20 〜 +5 | またぐ(差があるとは言えない) |
| mattpocock − perspectives | -17 | -32 〜 -5 | またがない |
| mattpocock − prove | +10 | +0 〜 +22 | またぐ(差があるとは言えない) |
| perspectives − prove | +27 | +12 〜 +41 | またがない |
