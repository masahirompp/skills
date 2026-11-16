## 構成の組み合わせ(1反復あたり。不具合は 41 件、題材は 10 件)

| 組み合わせ | 試行 | 検出した不具合(試行ごと) | 平均 | 本物でない余計な指摘 / 題材 | 本物の余計な指摘 / 題材 | 時間 / 題材 | 費用 / 題材 |
|---|---|---|---|---|---|---|---|
| perspectives | 1、2、3 | 21、18、20 | 19.7(48%) | 5.4 | 0.6 | 2.0分 | $0.58 |
| code-review | 1、2、3 | 22、16、14 | 17.3(42%) | 5.6 | 0.5 | 2.9分 | $0.58 |
| mattpocock | 1、2、3 | 12、8、11 | 10.3(25%) | 8.4 | 0.4 | 4.3分 | $1.13 |
| prove | 1、2、3 | 6、5、6 | 5.7(14%) | 0.1 | 0.1 | 4.2分 | $0.71 |
| security-review | 1、2、3 | 2、1、0 | 1.0(2%) | 0.0 | 0.0 | 0.8分 | $0.44 |
| code-review + perspectives | 1、2、3 | 27、25、24 | 25.3(62%) | 9.2 | 0.9 | 3.2分 | $1.16 |
| mattpocock + perspectives | 1、2、3 | 22、18、22 | 20.7(50%) | 12.8 | 0.9 | 4.4分 | $1.71 |
| perspectives + prove | 1、2、3 | 21、20、21 | 20.7(50%) | 5.4 | 0.7 | 4.4分 | $1.29 |
| code-review + mattpocock | 1、2、3 | 23、19、18 | 20.0(49%) | 12.3 | 0.7 | 5.0分 | $1.71 |
| security-review + perspectives | 1、2、3 | 21、18、20 | 19.7(48%) | 5.4 | 0.6 | 2.0分 | $1.02 |
| code-review + prove | 1、2、3 | 22、18、16 | 18.7(46%) | 5.6 | 0.5 | 4.8分 | $1.29 |
| code-review + security-review | 1、2、3 | 23、16、14 | 17.7(43%) | 5.6 | 0.5 | 2.9分 | $1.02 |
| mattpocock + prove | 1、2、3 | 13、11、14 | 12.7(31%) | 8.4 | 0.4 | 5.7分 | $1.84 |
| security-review + mattpocock | 1、2、3 | 14、8、11 | 11.0(27%) | 8.4 | 0.4 | 4.3分 | $1.57 |
| security-review + prove | 1、2、3 | 8、6、6 | 6.7(16%) | 0.1 | 0.1 | 4.2分 | $1.15 |
| code-review + mattpocock + perspectives | 1、2、3 | 28、25、26 | 26.3(64%) | 15.7 | 1.1 | 5.1分 | $2.29 |
| code-review + perspectives + prove | 1、2、3 | 27、25、25 | 25.7(63%) | 9.3 | 1.0 | 4.9分 | $1.87 |
| code-review + security-review + perspectives | 1、2、3 | 27、25、24 | 25.3(62%) | 9.2 | 0.9 | 3.2分 | $1.60 |
| mattpocock + perspectives + prove | 1、2、3 | 22、20、23 | 21.7(53%) | 12.8 | 0.9 | 5.7分 | $2.42 |
| code-review + mattpocock + prove | 1、2、3 | 23、19、20 | 20.7(50%) | 12.3 | 0.7 | 6.1分 | $2.42 |
| security-review + mattpocock + perspectives | 1、2、3 | 22、18、22 | 20.7(50%) | 12.8 | 0.9 | 4.4分 | $2.15 |
| security-review + perspectives + prove | 1、2、3 | 21、20、21 | 20.7(50%) | 5.4 | 0.7 | 4.4分 | $1.73 |
| code-review + security-review + mattpocock | 1、2、3 | 24、19、18 | 20.3(50%) | 12.3 | 0.7 | 5.0分 | $2.15 |
| code-review + security-review + prove | 1、2、3 | 23、18、16 | 19.0(46%) | 5.6 | 0.5 | 4.8分 | $1.73 |
| security-review + mattpocock + prove | 1、2、3 | 15、11、14 | 13.3(33%) | 8.4 | 0.4 | 5.7分 | $2.28 |
| code-review + mattpocock + perspectives + prove | 1、2、3 | 28、25、27 | 26.7(65%) | 15.7 | 1.2 | 6.2分 | $3.00 |
| code-review + security-review + mattpocock + perspectives | 1、2、3 | 28、25、26 | 26.3(64%) | 15.7 | 1.1 | 5.1分 | $2.73 |
| code-review + security-review + perspectives + prove | 1、2、3 | 27、25、25 | 25.7(63%) | 9.3 | 1.0 | 4.9分 | $2.31 |
| security-review + mattpocock + perspectives + prove | 1、2、3 | 22、20、23 | 21.7(53%) | 12.8 | 0.9 | 5.7分 | $2.86 |
| code-review + security-review + mattpocock + prove | 1、2、3 | 24、19、20 | 21.0(51%) | 12.3 | 0.7 | 6.1分 | $2.86 |
| code-review + security-review + mattpocock + perspectives + prove | 1、2、3 | 28、25、27 | 26.7(65%) | 15.7 | 1.2 | 6.2分 | $3.44 |

## 構成どうしの検出率の差(不具合を単位にしたブートストラップ、95% の幅)

| 比べる構成 | 差(ポイント) | 95% の幅 | 0 をまたぐか |
|---|---|---|---|
| code-review − security-review | +40 | +28 〜 +52 | またがない |
| code-review − mattpocock | +17 | +7 〜 +27 | またがない |
| code-review − perspectives | -6 | -17 〜 +6 | またぐ(差があるとは言えない) |
| code-review − prove | +28 | +18 〜 +39 | またがない |
| security-review − mattpocock | -23 | -35 〜 -12 | またがない |
| security-review − perspectives | -46 | -59 〜 -33 | またがない |
| security-review − prove | -11 | -21 〜 -3 | またがない |
| mattpocock − perspectives | -23 | -33 〜 -12 | またがない |
| mattpocock − prove | +11 | +2 〜 +21 | またがない |
| perspectives − prove | +34 | +23 〜 +46 | またがない |
