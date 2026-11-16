## code-review を繰り返した場合と、ほかの構成を足した場合(不具合は 41 件、題材は 10 件)

| 組み合わせ(構成#試行) | 検出した不具合 | 本物でない余計な指摘 / 題材 | 本物の余計な指摘 / 題材 | 時間 / 題材 | 費用 / 題材 |
|---|---|---|---|---|---|
| code-review#1 | 21(51%) | 5.2 | 0.7 | 2.6分 | $0.61 |
| code-review#2 | 21(51%) | 4.1 | 0.6 | 2.9分 | $0.59 |
| code-review#3 | 24(59%) | 4.9 | 0.5 | 3.1分 | $0.63 |
| code-review#1 + code-review#2 | 28(68%) | 7.6 | 1.0 | 3.3分 | $1.20 |
| code-review#1 + code-review#3 | 32(78%) | 7.7 | 1.1 | 3.2分 | $1.24 |
| code-review#2 + code-review#3 | 29(71%) | 7.0 | 0.8 | 3.3分 | $1.22 |
| code-review#1 + code-review#2 + code-review#3 | 33(80%) | 9.3 | 1.2 | 3.4分 | $1.83 |
| code-review#1 + security-review#1 | 21(51%) | 5.2 | 0.7 | 2.6分 | $1.01 |
| code-review#2 + security-review#1 | 21(51%) | 4.1 | 0.6 | 2.9分 | $0.99 |
| code-review#3 + security-review#1 | 25(61%) | 4.9 | 0.5 | 3.1分 | $1.03 |
| code-review#1 + mattpocock#1 | 22(54%) | 11.5 | 0.8 | 3.8分 | $1.69 |
| code-review#2 + mattpocock#1 | 21(51%) | 11.2 | 0.6 | 3.8分 | $1.67 |
| code-review#3 + mattpocock#1 | 26(63%) | 11.1 | 0.6 | 3.8分 | $1.71 |
| code-review#1 + perspectives#1 | 22(54%) | 9.5 | 1.1 | 2.7分 | $1.23 |
| code-review#2 + perspectives#1 | 23(56%) | 8.7 | 1.0 | 3.1分 | $1.22 |
| code-review#3 + perspectives#1 | 28(68%) | 8.9 | 1.0 | 3.1分 | $1.26 |
| code-review#1 + plain#1 | 24(59%) | 9.0 | 0.8 | 3.1分 | $1.16 |
| code-review#2 + plain#1 | 24(59%) | 8.6 | 0.8 | 3.1分 | $1.15 |
| code-review#3 + plain#1 | 29(71%) | 8.5 | 0.8 | 3.2分 | $1.19 |
| code-review#1 + prove#1 | 22(54%) | 5.2 | 0.7 | 4.2分 | $1.29 |
| code-review#2 + prove#1 | 21(51%) | 4.1 | 0.6 | 4.3分 | $1.28 |
| code-review#3 + prove#1 | 25(61%) | 4.9 | 0.5 | 4.4分 | $1.32 |
| code-review#1 + security-review#1 + mattpocock#1 | 22(54%) | 11.5 | 0.8 | 3.8分 | $2.09 |
| code-review#2 + security-review#1 + mattpocock#1 | 21(51%) | 11.2 | 0.6 | 3.8分 | $2.07 |
| code-review#3 + security-review#1 + mattpocock#1 | 27(66%) | 11.1 | 0.6 | 3.8分 | $2.11 |
| code-review#1 + security-review#1 + perspectives#1 | 22(54%) | 9.5 | 1.1 | 2.7分 | $1.63 |
| code-review#2 + security-review#1 + perspectives#1 | 23(56%) | 8.7 | 1.0 | 3.1分 | $1.62 |
| code-review#3 + security-review#1 + perspectives#1 | 28(68%) | 8.9 | 1.0 | 3.1分 | $1.66 |
| code-review#1 + security-review#1 + plain#1 | 24(59%) | 9.0 | 0.8 | 3.1分 | $1.56 |
| code-review#2 + security-review#1 + plain#1 | 24(59%) | 8.6 | 0.8 | 3.1分 | $1.55 |
| code-review#3 + security-review#1 + plain#1 | 29(71%) | 8.5 | 0.8 | 3.2分 | $1.59 |
| code-review#1 + security-review#1 + prove#1 | 22(54%) | 5.2 | 0.7 | 4.2分 | $1.69 |
| code-review#2 + security-review#1 + prove#1 | 21(51%) | 4.1 | 0.6 | 4.3分 | $1.68 |
| code-review#3 + security-review#1 + prove#1 | 26(63%) | 4.9 | 0.5 | 4.4分 | $1.72 |
| code-review#1 + mattpocock#1 + perspectives#1 | 23(56%) | 15.7 | 1.2 | 3.8分 | $2.32 |
| code-review#2 + mattpocock#1 + perspectives#1 | 23(56%) | 15.6 | 1.0 | 3.8分 | $2.30 |
| code-review#3 + mattpocock#1 + perspectives#1 | 28(68%) | 15.0 | 1.1 | 3.9分 | $2.34 |
| code-review#1 + mattpocock#1 + plain#1 | 24(59%) | 14.6 | 0.9 | 3.8分 | $2.25 |
| code-review#2 + mattpocock#1 + plain#1 | 24(59%) | 14.4 | 0.8 | 3.8分 | $2.23 |
| code-review#3 + mattpocock#1 + plain#1 | 29(71%) | 14.0 | 0.9 | 3.8分 | $2.27 |
| code-review#1 + mattpocock#1 + prove#1 | 23(56%) | 11.5 | 0.8 | 4.6分 | $2.37 |
| code-review#2 + mattpocock#1 + prove#1 | 21(51%) | 11.2 | 0.6 | 4.7分 | $2.36 |
| code-review#3 + mattpocock#1 + prove#1 | 26(63%) | 11.1 | 0.6 | 4.7分 | $2.40 |
| code-review#1 + perspectives#1 + plain#1 | 25(61%) | 12.2 | 1.2 | 3.1分 | $1.79 |
| code-review#2 + perspectives#1 + plain#1 | 25(61%) | 11.9 | 1.2 | 3.3分 | $1.78 |
| code-review#3 + perspectives#1 + plain#1 | 30(73%) | 11.3 | 1.3 | 3.3分 | $1.82 |
| code-review#1 + perspectives#1 + prove#1 | 23(56%) | 9.5 | 1.1 | 4.3分 | $1.92 |
| code-review#2 + perspectives#1 + prove#1 | 23(56%) | 8.7 | 1.0 | 4.4分 | $1.90 |
| code-review#3 + perspectives#1 + prove#1 | 28(68%) | 8.9 | 1.0 | 4.4分 | $1.94 |
| code-review#1 + plain#1 + prove#1 | 25(61%) | 9.0 | 0.8 | 4.2分 | $1.85 |
| code-review#2 + plain#1 + prove#1 | 24(59%) | 8.6 | 0.8 | 4.3分 | $1.83 |
| code-review#3 + plain#1 + prove#1 | 29(71%) | 8.5 | 0.8 | 4.4分 | $1.87 |
| code-review#1 + code-review#2 + security-review#1 | 28(68%) | 7.6 | 1.0 | 3.3分 | $1.60 |
| code-review#1 + code-review#2 + mattpocock#1 | 28(68%) | 13.8 | 1.0 | 4.0分 | $2.28 |
| code-review#1 + code-review#2 + perspectives#1 | 28(68%) | 11.4 | 1.3 | 3.3分 | $1.82 |
| code-review#1 + code-review#2 + plain#1 | 30(73%) | 11.0 | 1.1 | 3.4分 | $1.75 |
| code-review#1 + code-review#2 + prove#1 | 28(68%) | 7.6 | 1.0 | 4.3分 | $1.88 |
| code-review#1 + code-review#3 + security-review#1 | 32(78%) | 7.7 | 1.1 | 3.2分 | $1.64 |
| code-review#1 + code-review#3 + mattpocock#1 | 32(78%) | 13.6 | 1.2 | 3.9分 | $2.32 |
| code-review#1 + code-review#3 + perspectives#1 | 32(78%) | 11.3 | 1.4 | 3.3分 | $1.87 |
| code-review#1 + code-review#3 + plain#1 | 34(83%) | 10.7 | 1.2 | 3.4分 | $1.80 |
| code-review#1 + code-review#3 + prove#1 | 32(78%) | 7.7 | 1.1 | 4.4分 | $1.92 |
| code-review#2 + code-review#3 + security-review#1 | 29(71%) | 7.0 | 0.8 | 3.3分 | $1.62 |
| code-review#2 + code-review#3 + mattpocock#1 | 29(71%) | 13.2 | 0.8 | 4.0分 | $2.30 |
| code-review#2 + code-review#3 + perspectives#1 | 29(71%) | 10.8 | 1.2 | 3.4分 | $1.85 |
| code-review#2 + code-review#3 + plain#1 | 31(76%) | 10.4 | 1.0 | 3.5分 | $1.78 |
| code-review#2 + code-review#3 + prove#1 | 29(71%) | 7.0 | 0.8 | 4.4分 | $1.91 |

## code-review の全ての試行を合わせても見つからず、ほかの構成の試行1が見つけた不具合

- security-review: なし
- mattpocock: なし
- perspectives: なし
- plain: S13-8, S16-8
- prove: なし
