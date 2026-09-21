"""
scripts/issue_kakao_tokens.py
카카오 OAuth를 통해 영구 자동 갱신용 Refresh Token과 Access Token을 
일괄 발급받아 config.yaml에 자동으로 저장해 주는 도우미 스크립트.
"""

import sys
import ssl
import json
import webbrowser
import urllib.request
import urllib.parse
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.config import load_config, save_config


def main():
    print("=" * 70)
    print("   카카오톡 Access & Refresh Token 자동 발급 도우미")
    print("=" * 70)

    config = load_config()
    m_cfg = config.morning_report
    rest_key = m_cfg.kakao_rest_api_key.strip()
    if not rest_key or len(rest_key) != 32 or "/" in rest_key:
        rest_key = "10dd3be26f85a71a154f11220a776fcb"
        m_cfg.kakao_rest_api_key = rest_key
    print(f"• 카카오 REST API 키: {rest_key}")

    redirect_uri = "https://localhost"
    auth_url = (
        f"https://kauth.kakao.com/oauth/authorize"
        f"?client_id={rest_key}&redirect_uri={urllib.parse.quote(redirect_uri)}"
        f"&response_type=code&scope=talk_message"
    )

    print("\n1. 브라우저에서 카카오 인증 페이지가 열립니다...")
    print(f"   (열리지 않을 경우 수동 접속): {auth_url}")
    webbrowser.open(auth_url)

    print("\n2. 브라우저에서 '동의하고 계속하기'를 누르면 페이지가 이동합니다.")
    print("   ('이 사이트에 연결할 수 없음' 또는 'localhost' 에러 화면이 떠도 100% 정상입니다!)")
    print("3. 브라우저 주소창(URL)에 있는 주소를 그대로 복사해 주세요.")
    print("   예: https://localhost/?code=abc123xxxx...")

    code_input = input("\n주소창 URL (또는 code 값) 붙여넣기: ").strip()

    if "code=" in code_input:
        code = code_input.split("code=")[1].split("&")[0]
    else:
        code = code_input

    if not code:
        print("❌ 인가 코드가 입력되지 않았습니다.")
        return

    # Client Secret 확인 (KOE010 방지)
    client_secret = getattr(m_cfg, "kakao_client_secret", "").strip()
    
    # POST 토큰 요청
    token_url = "https://kauth.kakao.com/oauth/token"
    payload_dict = {
        "grant_type": "authorization_code",
        "client_id": rest_key,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    if client_secret:
        payload_dict["client_secret"] = client_secret
    data = urllib.parse.urlencode(payload_dict).encode("utf-8")

    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(
        token_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            tokens = json.loads(resp.read().decode("utf-8"))
            access = tokens.get("access_token")
            refresh = tokens.get("refresh_token")

            print("\n" + "=" * 70)
            print("🎉 카카오 토큰 발급 성공!")
            print("=" * 70)
            print(f"• Access Token : {access}")
            print(f"• Refresh Token: {refresh}")

            m_cfg.kakao_access_token = access
            if refresh:
                m_cfg.kakao_refresh_token = refresh
            save_config(config)

            print("\n✅ config.yaml 에 토큰이 자동으로 저장되었습니다!")
            print("이제 데스크톱 앱에서 [테스트 리포트 생성 및 카톡 즉시 발송]을 눌러보세요.")
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        if "KOE010" in err_msg:
            print("\n" + "!" * 70)
            print("⚠️ KOE010 오류: 카카오 개발자 콘솔에서 [클라이언트 시크릿]이 활성화되어 있습니다.")
            print("카카오 개발자 사이트의 [플랫폼 키 수정] 또는 [카카오 로그인 > 보안] 화면에서")
            print("1) '클라이언트 시크릿'을 '비활성화'로 끄시거나,")
            print("2) 화면에 발급된 '클라이언트 시크릿 코드'를 여기에 입력해 주세요.")
            print("!" * 70)
            secret_in = input("\n클라이언트 시크릿 코드 입력 (비활성화했으면 엔터): ").strip()
            if secret_in:
                payload_dict["client_secret"] = secret_in
            data_retry = urllib.parse.urlencode(payload_dict).encode("utf-8")
            req_retry = urllib.request.Request(
                token_url,
                data=data_retry,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req_retry, context=ctx, timeout=10) as resp2:
                    tokens = json.loads(resp2.read().decode("utf-8"))
                    access = tokens.get("access_token")
                    refresh = tokens.get("refresh_token")
                    print("\n" + "=" * 70)
                    print("🎉 카카오 토큰 발급 성공!")
                    print("=" * 70)
                    print(f"• Access Token : {access}")
                    print(f"• Refresh Token: {refresh}")
                    m_cfg.kakao_access_token = access
                    if refresh:
                        m_cfg.kakao_refresh_token = refresh
                    save_config(config)
                    print("\n✅ config.yaml 에 토큰이 자동으로 저장되었습니다!")
                    return
            except Exception as e2:
                print(f"재시도 실패: {e2}")
        else:
            print(f"\n❌ 토큰 발급 HTTP 오류 ({e.code}): {err_msg}")
    except Exception as e:
        print(f"\n❌ 토큰 발급 오류: {e}")


if __name__ == "__main__":
    main()
