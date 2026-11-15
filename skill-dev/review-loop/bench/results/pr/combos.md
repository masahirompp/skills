## 構成の組み合わせ(1反復あたり。不具合は 41 件、題材は 10 件)

| 組み合わせ | 検出した不具合(試行ごと) | 平均 | 本物でない余計な指摘 / 題材 | 本物の余計な指摘 / 題材 | 時間 / 題材 | 費用 / 題材 |
|---|---|---|---|---|---|---|
| code-review | 21、21、24 | 22.0(54%) | 4.7 | 0.6 | 2.9分 | $0.61 |
| perspectives | 16、19、19 | 18.0(44%) | 5.7 | 0.9 | 1.9分 | $0.60 |
| plain | 15、15、17 | 15.7(38%) | 5.1 | 0.4 | 1.8分 | $0.55 |
| mattpocock | 9、0、0 | 3.0(7%) | 2.6 | 0.1 | 1.1分 | $0.36 |
| prove | 5、0、0 | 1.7(4%) | 0.0 | 0.0 | 1.4分 | $0.23 |
| security-review | 2、0、0 | 0.7(2%) | 0.0 | 0.0 | 0.2分 | $0.13 |
| code-review + plain | 24、25、28 | 25.7(63%) | 8.3 | 0.8 | 3.0分 | $1.16 |
| code-review + perspectives | 22、25、28 | 25.0(61%) | 9.0 | 1.2 | 3.0分 | $1.21 |
| code-review + mattpocock | 22、21、24 | 22.3(54%) | 6.8 | 0.6 | 3.3分 | $0.97 |
| code-review + prove | 22、21、24 | 22.3(54%) | 4.7 | 0.6 | 3.4分 | $0.84 |
| code-review + security-review | 21、21、24 | 22.0(54%) | 4.7 | 0.6 | 2.9分 | $0.74 |
| perspectives + plain | 19、23、21 | 21.0(51%) | 8.8 | 1.2 | 2.2分 | $1.16 |
| mattpocock + perspectives | 17、19、19 | 18.3(45%) | 8.2 | 1.0 | 2.4分 | $0.96 |
| perspectives + prove | 17、19、19 | 18.3(45%) | 5.7 | 0.9 | 2.7分 | $0.83 |
| security-review + perspectives | 16、19、19 | 18.0(44%) | 5.7 | 0.9 | 1.9分 | $0.74 |
| mattpocock + plain | 16、15、17 | 16.0(39%) | 7.2 | 0.5 | 2.2分 | $0.91 |
| plain + prove | 16、15、17 | 16.0(39%) | 5.1 | 0.4 | 2.5分 | $0.78 |
| security-review + plain | 15、15、17 | 15.7(38%) | 5.1 | 0.4 | 1.8分 | $0.69 |
| security-review + mattpocock | 11、0、0 | 3.7(9%) | 2.6 | 0.1 | 1.1分 | $0.49 |
| mattpocock + prove | 10、0、0 | 3.3(8%) | 2.6 | 0.1 | 1.5分 | $0.59 |
| security-review + prove | 7、0、0 | 2.3(6%) | 0.0 | 0.0 | 1.4分 | $0.36 |
| code-review + perspectives + plain | 25、28、29 | 27.3(67%) | 11.4 | 1.4 | 3.1分 | $1.76 |
| code-review + plain + prove | 25、25、28 | 26.0(63%) | 8.3 | 0.8 | 3.4分 | $1.39 |
| code-review + security-review + plain | 24、25、28 | 25.7(63%) | 8.3 | 0.8 | 3.0分 | $1.30 |
| code-review + mattpocock + plain | 24、25、28 | 25.7(63%) | 10.1 | 0.9 | 3.3分 | $1.52 |
| code-review + mattpocock + perspectives | 23、25、28 | 25.3(62%) | 11.1 | 1.3 | 3.4分 | $1.57 |
| code-review + perspectives + prove | 23、25、28 | 25.3(62%) | 9.0 | 1.2 | 3.5分 | $1.44 |
| code-review + security-review + perspectives | 22、25、28 | 25.0(61%) | 9.0 | 1.2 | 3.0分 | $1.35 |
| code-review + mattpocock + prove | 23、21、24 | 22.7(55%) | 6.8 | 0.6 | 3.5分 | $1.20 |
| code-review + security-review + mattpocock | 22、21、24 | 22.3(54%) | 6.8 | 0.6 | 3.3分 | $1.10 |
| code-review + security-review + prove | 22、21、24 | 22.3(54%) | 4.7 | 0.6 | 3.4分 | $0.97 |
| perspectives + plain + prove | 20、23、21 | 21.3(52%) | 8.8 | 1.2 | 2.7分 | $1.38 |
| security-review + perspectives + plain | 19、23、21 | 21.0(51%) | 8.8 | 1.2 | 2.2分 | $1.29 |
| mattpocock + perspectives + plain | 19、23、21 | 21.0(51%) | 10.8 | 1.2 | 2.5分 | $1.52 |
| mattpocock + perspectives + prove | 18、19、19 | 18.7(46%) | 8.2 | 1.0 | 2.8分 | $1.19 |
| security-review + mattpocock + perspectives | 17、19、19 | 18.3(45%) | 8.2 | 1.0 | 2.4分 | $1.10 |
| security-review + perspectives + prove | 17、19、19 | 18.3(45%) | 5.7 | 0.9 | 2.7分 | $0.96 |
| mattpocock + plain + prove | 17、15、17 | 16.3(40%) | 7.2 | 0.5 | 2.6分 | $1.14 |
| security-review + mattpocock + plain | 16、15、17 | 16.0(39%) | 7.2 | 0.5 | 2.2分 | $1.05 |
| security-review + plain + prove | 16、15、17 | 16.0(39%) | 5.1 | 0.4 | 2.5分 | $0.91 |
| security-review + mattpocock + prove | 12、0、0 | 4.0(10%) | 2.6 | 0.1 | 1.5分 | $0.72 |
| code-review + perspectives + plain + prove | 26、28、29 | 27.7(67%) | 11.4 | 1.4 | 3.5分 | $1.99 |
| code-review + security-review + perspectives + plain | 25、28、29 | 27.3(67%) | 11.4 | 1.4 | 3.1分 | $1.90 |
| code-review + mattpocock + perspectives + plain | 25、28、29 | 27.3(67%) | 13.3 | 1.4 | 3.4分 | $2.13 |
| code-review + security-review + plain + prove | 25、25、28 | 26.0(63%) | 8.3 | 0.8 | 3.4分 | $1.52 |
| code-review + mattpocock + plain + prove | 25、25、28 | 26.0(63%) | 10.1 | 0.9 | 3.5分 | $1.75 |
| code-review + security-review + mattpocock + plain | 24、25、28 | 25.7(63%) | 10.1 | 0.9 | 3.3分 | $1.66 |
| code-review + mattpocock + perspectives + prove | 24、25、28 | 25.7(63%) | 11.1 | 1.3 | 3.7分 | $1.80 |
| code-review + security-review + mattpocock + perspectives | 23、25、28 | 25.3(62%) | 11.1 | 1.3 | 3.4分 | $1.71 |
| code-review + security-review + perspectives + prove | 23、25、28 | 25.3(62%) | 9.0 | 1.2 | 3.5分 | $1.57 |
| code-review + security-review + mattpocock + prove | 23、21、24 | 22.7(55%) | 6.8 | 0.6 | 3.5分 | $1.33 |
| security-review + perspectives + plain + prove | 20、23、21 | 21.3(52%) | 8.8 | 1.2 | 2.7分 | $1.52 |
| mattpocock + perspectives + plain + prove | 20、23、21 | 21.3(52%) | 10.8 | 1.2 | 2.9分 | $1.74 |
| security-review + mattpocock + perspectives + plain | 19、23、21 | 21.0(51%) | 10.8 | 1.2 | 2.5分 | $1.65 |
| security-review + mattpocock + perspectives + prove | 18、19、19 | 18.7(46%) | 8.2 | 1.0 | 2.8分 | $1.32 |
| security-review + mattpocock + plain + prove | 17、15、17 | 16.3(40%) | 7.2 | 0.5 | 2.6分 | $1.27 |
| code-review + security-review + perspectives + plain + prove | 26、28、29 | 27.7(67%) | 11.4 | 1.4 | 3.5分 | $2.13 |
| code-review + mattpocock + perspectives + plain + prove | 26、28、29 | 27.7(67%) | 13.3 | 1.4 | 3.7分 | $2.35 |
| code-review + security-review + mattpocock + perspectives + plain | 25、28、29 | 27.3(67%) | 13.3 | 1.4 | 3.4分 | $2.26 |
| code-review + security-review + mattpocock + plain + prove | 25、25、28 | 26.0(63%) | 10.1 | 0.9 | 3.5分 | $1.88 |
| code-review + security-review + mattpocock + perspectives + prove | 24、25、28 | 25.7(63%) | 11.1 | 1.3 | 3.7分 | $1.93 |
| security-review + mattpocock + perspectives + plain + prove | 20、23、21 | 21.3(52%) | 10.8 | 1.2 | 2.9分 | $1.88 |
| code-review + security-review + mattpocock + perspectives + plain + prove | 26、28、29 | 27.7(67%) | 13.3 | 1.4 | 3.7分 | $2.49 |

## 構成どうしの検出率の差(不具合を単位にしたブートストラップ、95% の幅)

| 比べる構成 | 差(ポイント) | 95% の幅 | 0 をまたぐか |
|---|---|---|---|
| code-review − security-review | +52 | +41 〜 +63 | またがない |
| code-review − mattpocock | +46 | +37 〜 +56 | またがない |
| code-review − perspectives | +10 | +2 〜 +18 | またがない |
| code-review − plain | +15 | +6 〜 +25 | またがない |
| code-review − prove | +50 | +40 〜 +59 | またがない |
| security-review − mattpocock | -6 | -11 〜 -1 | またがない |
| security-review − perspectives | -42 | -54 〜 -29 | またがない |
| security-review − plain | -37 | -50 〜 -24 | またがない |
| security-review − prove | -2 | -7 〜 +2 | またぐ(差があるとは言えない) |
| mattpocock − perspectives | -37 | -48 〜 -26 | またがない |
| mattpocock − plain | -31 | -42 〜 -21 | またがない |
| mattpocock − prove | +3 | +0 〜 +7 | またぐ(差があるとは言えない) |
| perspectives − plain | +6 | -4 〜 +15 | またぐ(差があるとは言えない) |
| perspectives − prove | +40 | +28 〜 +52 | またがない |
| plain − prove | +34 | +21 〜 +46 | またがない |
