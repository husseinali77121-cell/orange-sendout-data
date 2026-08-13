# -*- coding: utf-8 -*-
"""
Orange Lab Send-Out — مولّد كلمات المرور
شغّله كده:  python make_hash.py

بيطبعلك بلوك جاهز تلزقه في .streamlit/secrets.toml
"""

import getpass
import hashlib
import secrets as _s


def hash_password(pw: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120_000).hex()


def main():
    print("=" * 58)
    print("مولّد مستخدمي Orange Lab")
    print("=" * 58)

    salt = input("\nالـ salt (سيبها فاضية لتوليد واحدة جديدة): ").strip()
    if not salt:
        salt = _s.token_hex(16)
        print(f"اتولّدت salt جديدة: {salt}")
        print("⚠️ نفس الـ salt لازم تفضل ثابتة — لو غيّرتها كل الباسوردات هتبطل.")

    users = []
    while True:
        print("\n" + "-" * 58)
        uname = input("اسم المستخدم (Enter للإنهاء): ").strip().lower()
        if not uname:
            break
        name = input("الاسم الكامل: ").strip()
        print("الفرع:  1) دياموند   2) لاسيتيه")
        branch = "DIAMOND" if input("اختر [1/2]: ").strip() != "2" else "LACITE"
        print("الدور:  1) استقبال  2) فني معمل  3) مدير المعمل  4) مدير النظام")
        role = {"1": "reception", "2": "tech",
                "3": "director", "4": "admin"}.get(input("اختر [1-4]: ").strip(), "reception")
        pw = getpass.getpass("كلمة المرور: ")
        if not pw:
            print("⚠️ كلمة مرور فاضية — اتخطّى المستخدم ده.")
            continue
        users.append((uname, name, branch, role, hash_password(pw, salt)))
        print(f"✅ اتضاف: {uname}")

    if not users:
        print("\nمفيش مستخدمين اتضافوا.")
        return

    print("\n" + "=" * 58)
    print("الزق ده في .streamlit/secrets.toml")
    print("=" * 58 + "\n")
    print(f'password_salt = "{salt}"\n')
    print('# للتخزين على GitHub (سيبهم متعلّقين للتخزين المحلي)')
    print('# github_token  = "ghp_..."')
    print('# github_repo   = "username/orange-sendout-data"')
    print('# github_branch = "main"\n')
    for uname, name, branch, role, h in users:
        print(f'[users.{uname}]')
        print(f'name = "{name}"')
        print(f'branch = "{branch}"')
        print(f'role = "{role}"')
        print(f'password_hash = "{h}"\n')


if __name__ == "__main__":
    main()
