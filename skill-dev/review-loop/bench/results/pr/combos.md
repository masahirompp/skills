## 構成の組み合わせ(1反復あたり。不具合は 41 件、題材は 10 件)

構成によって、回した試行が違う。組み合わせの行は、その全ての構成にある試行だけの値(列「試行」)なので、
試行の違う行どうしは、平均、時間、費用を比べられない。

| 組み合わせ | 試行 | 検出した不具合(試行ごと) | 平均 | 本物でない余計な指摘 / 題材 | 本物の余計な指摘 / 題材 | 時間 / 題材 | 費用 / 題材 |
|---|---|---|---|---|---|---|---|
| code-review | 1、2、3 | 21、21、24 | 22.0(54%) | 4.7 | 0.6 | 2.9分 | $0.61 |
| perspectives | 1、2、3 | 16、19、19 | 18.0(44%) | 5.7 | 0.9 | 1.9分 | $0.60 |
| plain | 1、2、3 | 15、15、17 | 15.7(38%) | 5.1 | 0.4 | 1.8分 | $0.55 |
| mattpocock | 1 | 9 | 9.0(22%) | 7.9 | 0.2 | 3.4分 | $1.08 |
| prove | 1 | 5 | 5.0(12%) | 0.0 | 0.1 | 4.1分 | $0.68 |
| security-review | 1 | 2 | 2.0(5%) | 0.0 | 0.0 | 0.7分 | $0.40 |
| code-review + plain | 1、2、3 | 24、25、28 | 25.7(63%) | 8.3 | 0.8 | 3.0分 | $1.16 |
| code-review + perspectives | 1、2、3 | 22、25、28 | 25.0(61%) | 9.0 | 1.2 | 3.0分 | $1.21 |
| code-review + mattpocock | 1 | 22 | 22.0(54%) | 11.5 | 0.8 | 3.8分 | $1.69 |
| code-review + prove | 1 | 22 | 22.0(54%) | 5.2 | 0.7 | 4.2分 | $1.29 |
| code-review + security-review | 1 | 21 | 21.0(51%) | 5.2 | 0.7 | 2.6分 | $1.01 |
| perspectives + plain | 1、2、3 | 19、23、21 | 21.0(51%) | 8.8 | 1.2 | 2.2分 | $1.16 |
| mattpocock + perspectives | 1 | 17 | 17.0(41%) | 13.1 | 0.8 | 3.5分 | $1.71 |
| perspectives + prove | 1 | 17 | 17.0(41%) | 5.7 | 0.7 | 4.3分 | $1.31 |
| security-review + perspectives | 1 | 16 | 16.0(39%) | 5.7 | 0.7 | 2.0分 | $1.03 |
| mattpocock + plain | 1 | 16 | 16.0(39%) | 11.7 | 0.5 | 3.4分 | $1.64 |
| plain + prove | 1 | 16 | 16.0(39%) | 5.5 | 0.4 | 4.2分 | $1.24 |
| security-review + plain | 1 | 15 | 15.0(37%) | 5.5 | 0.4 | 2.2分 | $0.96 |
| security-review + mattpocock | 1 | 11 | 11.0(27%) | 7.9 | 0.2 | 3.4分 | $1.48 |
| mattpocock + prove | 1 | 10 | 10.0(24%) | 7.9 | 0.2 | 4.6分 | $1.77 |
| security-review + prove | 1 | 7 | 7.0(17%) | 0.0 | 0.1 | 4.1分 | $1.08 |
| code-review + perspectives + plain | 1、2、3 | 25、28、29 | 27.3(67%) | 11.4 | 1.4 | 3.1分 | $1.76 |
| code-review + plain + prove | 1 | 25 | 25.0(61%) | 9.0 | 0.8 | 4.2分 | $1.85 |
| code-review + security-review + plain | 1 | 24 | 24.0(59%) | 9.0 | 0.8 | 3.1分 | $1.56 |
| code-review + mattpocock + plain | 1 | 24 | 24.0(59%) | 14.6 | 0.9 | 3.8分 | $2.25 |
| code-review + mattpocock + perspectives | 1 | 23 | 23.0(56%) | 15.7 | 1.2 | 3.8分 | $2.32 |
| code-review + mattpocock + prove | 1 | 23 | 23.0(56%) | 11.5 | 0.8 | 4.6分 | $2.37 |
| code-review + perspectives + prove | 1 | 23 | 23.0(56%) | 9.5 | 1.1 | 4.3分 | $1.92 |
| code-review + security-review + mattpocock | 1 | 22 | 22.0(54%) | 11.5 | 0.8 | 3.8分 | $2.09 |
| code-review + security-review + perspectives | 1 | 22 | 22.0(54%) | 9.5 | 1.1 | 2.7分 | $1.63 |
| code-review + security-review + prove | 1 | 22 | 22.0(54%) | 5.2 | 0.7 | 4.2分 | $1.69 |
| perspectives + plain + prove | 1 | 20 | 20.0(49%) | 9.3 | 1.0 | 4.3分 | $1.87 |
| security-review + perspectives + plain | 1 | 19 | 19.0(46%) | 9.3 | 1.0 | 2.6分 | $1.59 |
| mattpocock + perspectives + plain | 1 | 19 | 19.0(46%) | 15.3 | 1.1 | 3.5分 | $2.27 |
| mattpocock + perspectives + prove | 1 | 18 | 18.0(44%) | 13.1 | 0.8 | 4.7分 | $2.39 |
| security-review + mattpocock + perspectives | 1 | 17 | 17.0(41%) | 13.1 | 0.8 | 3.5分 | $2.11 |
| security-review + perspectives + prove | 1 | 17 | 17.0(41%) | 5.7 | 0.7 | 4.3分 | $1.71 |
| mattpocock + plain + prove | 1 | 17 | 17.0(41%) | 11.7 | 0.5 | 4.6分 | $2.32 |
| security-review + mattpocock + plain | 1 | 16 | 16.0(39%) | 11.7 | 0.5 | 3.4分 | $2.04 |
| security-review + plain + prove | 1 | 16 | 16.0(39%) | 5.5 | 0.4 | 4.2分 | $1.64 |
| security-review + mattpocock + prove | 1 | 12 | 12.0(29%) | 7.9 | 0.2 | 4.6分 | $2.17 |
| code-review + perspectives + plain + prove | 1 | 26 | 26.0(63%) | 12.2 | 1.2 | 4.3分 | $2.48 |
| code-review + security-review + perspectives + plain | 1 | 25 | 25.0(61%) | 12.2 | 1.2 | 3.1分 | $2.19 |
| code-review + security-review + plain + prove | 1 | 25 | 25.0(61%) | 9.0 | 0.8 | 4.2分 | $2.25 |
| code-review + mattpocock + perspectives + plain | 1 | 25 | 25.0(61%) | 17.8 | 1.3 | 3.8分 | $2.87 |
| code-review + mattpocock + plain + prove | 1 | 25 | 25.0(61%) | 14.6 | 0.9 | 4.6分 | $2.93 |
| code-review + security-review + mattpocock + plain | 1 | 24 | 24.0(59%) | 14.6 | 0.9 | 3.8分 | $2.65 |
| code-review + mattpocock + perspectives + prove | 1 | 24 | 24.0(59%) | 15.7 | 1.2 | 4.7分 | $3.00 |
| code-review + security-review + mattpocock + perspectives | 1 | 23 | 23.0(56%) | 15.7 | 1.2 | 3.8分 | $2.72 |
| code-review + security-review + mattpocock + prove | 1 | 23 | 23.0(56%) | 11.5 | 0.8 | 4.6分 | $2.77 |
| code-review + security-review + perspectives + prove | 1 | 23 | 23.0(56%) | 9.5 | 1.1 | 4.3分 | $2.32 |
| security-review + perspectives + plain + prove | 1 | 20 | 20.0(49%) | 9.3 | 1.0 | 4.3分 | $2.27 |
| mattpocock + perspectives + plain + prove | 1 | 20 | 20.0(49%) | 15.3 | 1.1 | 4.7分 | $2.95 |
| security-review + mattpocock + perspectives + plain | 1 | 19 | 19.0(46%) | 15.3 | 1.1 | 3.5分 | $2.67 |
| security-review + mattpocock + perspectives + prove | 1 | 18 | 18.0(44%) | 13.1 | 0.8 | 4.7分 | $2.79 |
| security-review + mattpocock + plain + prove | 1 | 17 | 17.0(41%) | 11.7 | 0.5 | 4.6分 | $2.72 |
| code-review + security-review + perspectives + plain + prove | 1 | 26 | 26.0(63%) | 12.2 | 1.2 | 4.3分 | $2.88 |
| code-review + mattpocock + perspectives + plain + prove | 1 | 26 | 26.0(63%) | 17.8 | 1.3 | 4.7分 | $3.56 |
| code-review + security-review + mattpocock + perspectives + plain | 1 | 25 | 25.0(61%) | 17.8 | 1.3 | 3.8分 | $3.27 |
| code-review + security-review + mattpocock + plain + prove | 1 | 25 | 25.0(61%) | 14.6 | 0.9 | 4.6分 | $3.33 |
| code-review + security-review + mattpocock + perspectives + prove | 1 | 24 | 24.0(59%) | 15.7 | 1.2 | 4.7分 | $3.40 |
| security-review + mattpocock + perspectives + plain + prove | 1 | 20 | 20.0(49%) | 15.3 | 1.1 | 4.7分 | $3.35 |
| code-review + security-review + mattpocock + perspectives + plain + prove | 1 | 26 | 26.0(63%) | 17.8 | 1.3 | 4.7分 | $3.96 |

## 構成どうしの検出率の差(不具合を単位にしたブートストラップ、95% の幅)

| 比べる構成 | 差(ポイント) | 95% の幅 | 0 をまたぐか |
|---|---|---|---|
| code-review − security-review | +49 | +37 〜 +60 | またがない |
| code-review − mattpocock | +32 | +20 〜 +43 | またがない |
| code-review − perspectives | +10 | +2 〜 +18 | またがない |
| code-review − plain | +15 | +6 〜 +25 | またがない |
| code-review − prove | +41 | +29 〜 +53 | またがない |
| security-review − mattpocock | -17 | -32 〜 -2 | またがない |
| security-review − perspectives | -39 | -52 〜 -26 | またがない |
| security-review − plain | -33 | -46 〜 -21 | またがない |
| security-review − prove | -7 | -20 〜 +5 | またぐ(差があるとは言えない) |
| mattpocock − perspectives | -22 | -34 〜 -11 | またがない |
| mattpocock − plain | -16 | -27 〜 -7 | またがない |
| mattpocock − prove | +10 | +0 〜 +22 | またぐ(差があるとは言えない) |
| perspectives − plain | +6 | -4 〜 +15 | またぐ(差があるとは言えない) |
| perspectives − prove | +32 | +19 〜 +45 | またがない |
| plain − prove | +26 | +12 〜 +40 | またがない |
