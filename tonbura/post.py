#!/usr/bin/env python3
"""とんぶらリール（@tonburafiba）を Instagram に投稿する。トークンは環境変数から読むだけで、表示しない。
使い方: python3 tonbura/post.py YYYYMMDD [--dry-run]
  tonbura/YYYYMMDD.mp4・tonbura/YYYYMMDD.md（そのまま投稿文）・tonbura/YYYYMMDD_cover.jpg（カバー＝サムネ、必須）を使う。
  動画はこのリポジトリ（公開）の raw URL を渡す。投稿済みの日付は tonbura/posted.txt に書く。
必要な環境変数: IG_ACCESS_TOKEN（@tonburafiba、Instagramログイン方式）。IG_USER_ID は無ければ /me から取る。
"""
import json, os, sys, time, urllib.parse, urllib.request

API = 'https://graph.instagram.com/v21.0'
RAW = 'https://raw.githubusercontent.com/tonbura-dot/tonzura-media/main/tonbura/'
HERE = os.path.dirname(os.path.abspath(__file__))
WANT_USER = 'tonburafiba'


def call(method, path, **params):
    params['access_token'] = os.environ['IG_ACCESS_TOKEN'].strip()
    data = urllib.parse.urlencode(params).encode()
    url = f'{API}/{path}'
    if method == 'GET':
        req = urllib.request.Request(url + '?' + data.decode())
    else:
        req = urllib.request.Request(url, data=data, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace').replace(params['access_token'], '***')
        sys.exit(f'APIエラー {e.code} {path}: {body[:500]}')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    dry = '--dry-run' in sys.argv
    if not args: sys.exit(__doc__)
    day = args[0]
    mp4, md = f'{HERE}/{day}.mp4', f'{HERE}/{day}.md'
    if not (os.path.exists(mp4) and os.path.exists(md)): sys.exit(f'{day}: 動画か投稿文がまだ無い')
    posted = f'{HERE}/posted.txt'
    if os.path.exists(posted) and any(l.split()[0] == day for l in open(posted) if l.strip()):
        sys.exit(f'{day}: もう投稿済み')
    caption = open(md, encoding='utf-8').read().strip()
    if not os.environ.get('IG_ACCESS_TOKEN'): sys.exit('IG_ACCESS_TOKEN がありません（クラウド環境の環境変数を確認）')
    me = call('GET', 'me', fields='user_id,username')
    if me.get('username') != WANT_USER: sys.exit(f'トークンのアカウントが {me.get("username")} で、{WANT_USER} ではないので止めた')
    uid = os.environ.get('IG_USER_ID', '').strip() or str(me['user_id'])
    print('account ok:', me['username'])
    if dry:
        print('dry-run: 投稿はしない', RAW + f'{day}.mp4'); return
    extra = {}
    if os.path.exists(f'{HERE}/{day}_cover.jpg'): extra['cover_url'] = RAW + f'{day}_cover.jpg'
    else: sys.exit(f'{day}: カバー画像 {day}_cover.jpg が無いので投稿しない（サムネなしで出さない）')
    c = call('POST', f'{uid}/media', media_type='REELS', video_url=RAW + f'{day}.mp4', caption=caption, share_to_feed='true', **extra)
    cid = c['id']
    for _ in range(60):
        st = call('GET', cid, fields='status_code,status').get('status_code')
        if st == 'FINISHED': break
        if st == 'ERROR': sys.exit(f'動画の処理でエラー: {call("GET", cid, fields="status")}')
        time.sleep(10)
    else:
        sys.exit('10分待っても処理が終わらない')
    mid = call('POST', f'{uid}/media_publish', creation_id=cid)['id']
    link = call('GET', mid, fields='permalink').get('permalink', '')
    with open(posted, 'a') as f: f.write(f'{day} {link}\n')
    print('posted', day, link)


if __name__ == '__main__':
    main()
