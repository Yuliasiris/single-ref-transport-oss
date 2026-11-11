# Gitへの送信結果が不明なとき、もう一度送る前に

AIエージェントや自動処理がGitへ変更を送ったあと、応答が切れたとします。変更が届かなかったのか、届いたのに応答だけ失われたのかは、エラー表示だけでは分かりません。

Single-ref Transportは、**一つのブランチへの条件付き更新と、その後の読戻し**を扱う小さなPythonライブラリです。Gitそのもの、認証、ジョブ管理、AIの起動を置き換えません。

## まず試す

Python 3.10以上とGitが必要です。このガイドの追加例はソースチェックアウト向けです。既存v0.2.2の配布ZIPに含まれているとは限りません。

このガイドと同じブランチ／commitのソースで、リポジトリのルートから実行します。

```sh
python examples/recovery_walkthrough.py
```

既存の作業リポジトリやGitHubアカウントは使いません。一時ディレクトリ内に作業用・bareリポジトリを作り、実Gitで更新し、終了時に削除します。任意の送信先を指定する引数はありません。第三者Python依存は不要です。

出力の要点は次の四つです。

```text
normal: updated; push attempts = 1
stale preimage: conflict; push attempts = 0
injected lost ack: observed_candidate; push attempts = 1
separate-process readback: observed_candidate; push attempts = 0
```

1. 通常の更新では、送信の成功応答と、候補commitの存在を両方確認します。
2. 読んでいた古いcommitと実際のブランチが違えば、更新しません。
3. 実際のローカルpush成功後に、例が意図的に応答喪失を注入します。候補は観測できますが、受け取っていない成功応答を作りません。
4. 記録をファイルへ保存し、別のPythonプロセスで読み直します。この回復処理は読むだけで、pushできません。

機械可読の出力は `python examples/recovery_walkthrough.py --json` です。例の回帰検査は `python -m unittest -v test_recovery_walkthrough` で実行できます。

## 何に使うか

変更候補と更新先をホスト側で決めたあと、送信直前の古いcommitとの一致を条件に一回だけ更新したい場面に向きます。不明な応答の後に、無条件で同じ更新を繰り返したくない場合にも使えます。

`observed_candidate` は「候補がそこにある」です。「この実行者が送ったと証明できた」「受取人が仕事を始めた」「利用者が採用した」ではありません。観測と承認を混ぜないため、状態を分けています。

## ホスト側に残る責任

ホストは、許可したrepository、完全なbranch ref、candidate、expected old commitを独立に決めます。利用者から来た要求を、そのまま許可情報としてコピーしないでください。認証情報、フック、Git設定、同時実行の管理もホスト側の責任です。

このライブラリは遠隔でのexactly-onceを保証しません。タグ、削除、履歴の強制書換え、複数refの一括取引、SHA-256形式のGitリポジトリは対象外です。例の成功は、全OS・全Gitバージョンやクラウド間の自律運用の合格ではありません。

完全なAPIと状態の意味は [README](../../README.md)、安全上の境界は [SECURITY](../../SECURITY.md) にあります。コードはMITライセンスです。

## 試した結果を教えてください

導入できたかだけでも役に立ちます。問題があれば、OS、Python/Gitのバージョン、実行コマンド、期待した結果と実際の結果を [Issues](https://github.com/Yuliasiris/single-ref-transport-oss/issues) へお願いします。送信先やログに秘密・個人情報が含まれる場合は、取り除いてください。

「既存のGitコマンドだけで十分だった」「こういう状態が欲しい」という意見も歓迎します。スターは関心の表明として任意です。利用実績や品質の証明とは分けて扱います。
