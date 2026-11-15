"""4角女神 BGM 作曲スクリプト（全曲オリジナル。MIDIを書いて FluidR3_GM で音にする）"""
import mido, os, random

NOTE = {'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}
def n(s):
    s = s.strip(); p = NOTE[s[0]]; i = 1
    while i < len(s) and s[i] in '#b':
        p += 1 if s[i] == '#' else -1; i += 1
    return p + 12 * (int(s[i:]) + 1)

class Song:
    def __init__(self, bpm):
        self.bpm = bpm; self.ev = []; self.prog = {}
    def program(self, ch, prog):
        self.prog[ch] = prog
    def note(self, ch, pitch, start, dur, vel=90):
        if isinstance(pitch, str): pitch = n(pitch)
        self.ev.append((start, 1, ch, pitch, vel)); self.ev.append((start + dur * 0.98, 0, ch, pitch, 0))
    def chord(self, ch, pitches, start, dur, vel=80):
        for p in pitches: self.note(ch, p, start, dur, vel)
    def melody(self, ch, text, start, vel=95, oct_shift=0):
        t = start
        for tok in text.split():
            name, d = tok.split(':'); d = eval(d)
            if name != 'R': self.note(ch, n(name) + 12 * oct_shift, t, d, vel)
            t += d
        return t
    def bend(self, ch, start, value):
        self.ev.append((start, 2, ch, value, 0))
    def cc(self, ch, start, ctl, value):
        self.ev.append((start, 3, ch, ctl, value))
    def drum(self, pitch, start, vel=100, dur=0.25):
        self.note(9, pitch, start, dur, vel)
    def save(self, path, tail=2.0):
        mid = mido.MidiFile(ticks_per_beat=480); tr = mido.MidiTrack(); mid.tracks.append(tr)
        tr.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(self.bpm)))
        for ch, pg in self.prog.items():
            tr.append(mido.Message('program_change', channel=ch, program=pg))
            tr.append(mido.Message('control_change', channel=ch, control=91, value=45))  # reverb
        ev = sorted(self.ev, key=lambda e: (e[0], e[1]))
        last = 0
        for t, kind, ch, a, b in ev:
            tick = int(round(t * 480)); dt = max(0, tick - last); last = max(last, tick)
            if kind == 1: m = mido.Message('note_on', channel=ch, note=a, velocity=b, time=dt)
            elif kind == 0: m = mido.Message('note_off', channel=ch, note=a, velocity=0, time=dt)
            elif kind == 2: m = mido.Message('pitchwheel', channel=ch, pitch=a, time=dt)
            else: m = mido.Message('control_change', channel=ch, control=a, value=b, time=dt)
            tr.append(m)
        tr.append(mido.MetaMessage('end_of_track', time=int(tail * 480 * self.bpm / 60)))
        mid.save(path)

KICK, SNARE, CLAP, RIM, HHC, HHO, CRASH, RIDE, TOMH, TOML, SHAKER, WOOD = 36, 38, 39, 37, 42, 46, 49, 51, 50, 45, 70, 76
def tri(root, kind='maj'):
    r = n(root) if isinstance(root, str) else root
    iv = {'maj': [0,4,7], 'min': [0,3,7], 'maj7': [0,4,7,11], 'm7': [0,3,7,10], '7': [0,4,7,10], 'sus4':[0,5,7], 'dim':[0,3,6]}[kind]
    return [r + i for i in iv]

OUT = '/tmp/claude-0/bgm/mid'
random.seed(7)

# ========== ① オープニング/締めジングル ==========
def jingle_a():  # ピコピコ・ポップ（スクエアリード＋ストリングス）
    s = Song(152)
    s.program(0, 80); s.program(1, 81); s.program(2, 48); s.program(3, 38); s.program(4, 9)
    prog = [('C4','maj'),('G3','maj'),('A3','min'),('F3','maj'),('C4','maj'),('G3','maj'),('F3','maj'),('G3','maj')]
    for bar, (r, k) in enumerate(prog):
        b = bar * 2
        ch = tri(r, k)
        s.chord(2, [p + 12 for p in ch], b, 2, 60)
        s.note(3, ch[0] - 12, b, 0.5, 100); s.note(3, ch[0] - 12, b + 0.75, 0.25, 90); s.note(3, ch[0], b + 1, 0.5, 90); s.note(3, ch[0] - 12, b + 1.5, 0.5, 90)
        for i in range(8):
            s.note(1, ch[i % 3] + 24, b + i * 0.25, 0.2, 55)
        s.drum(KICK, b, 110); s.drum(KICK, b + 1, 105); s.drum(CLAP, b + 1, 90); s.drum(SNARE, b + 1, 70)
        for i in range(4): s.drum(HHC, b + i * 0.5, 60)
    s.drum(CRASH, 0, 110)
    s.melody(0, "E5:0.5 G5:0.5 C6:0.75 B5:0.25 | D6:0.5 B5:0.5 G5:1 | A5:0.5 C6:0.5 E6:0.75 D6:0.25 | C6:0.5 A5:0.5 F5:1 "
                "| E5:0.5 G5:0.5 C6:0.5 E6:0.5 | D6:0.75 C6:0.25 B5:1 | A5:0.5 C6:0.5 F6:0.5 E6:0.5 | D6:0.5 E6:0.25 F6:0.25 G6:1".replace('| ', ''), 0, 100)
    # 決めの一発
    s.chord(2, [n('C5'), n('E5'), n('G5'), n('C6')], 16, 3, 90); s.chord(0, [n('C6'), n('G6')], 16, 1.5, 105)
    s.note(3, 'C2', 16, 2, 110); s.drum(CRASH, 16, 120); s.drum(KICK, 16, 120)
    s.note(4, 'C7', 16, 1, 90); s.note(4, 'G6', 16.25, 1, 80); s.note(4, 'C7', 16.5, 1.5, 90)
    s.save(f'{OUT}/1_jingle_A.mid', 2.5)

def jingle_b():  # キラキラ・ベル系（グロッケン＋シンセ）
    s = Song(140)
    s.program(0, 9); s.program(1, 88); s.program(2, 33); s.program(3, 98); s.program(4, 80)
    prog = [('F3','maj'),('G3','maj'),('E3','min'),('A3','min'),('D3','min'),('G3','maj'),('C4','maj'),('C4','maj')]
    for bar, (r, k) in enumerate(prog):
        b = bar * 2; ch = tri(r, k)
        s.chord(1, [p + 12 for p in ch], b, 2, 60)
        s.note(2, ch[0] - 12, b, 0.75, 95); s.note(2, ch[0] - 12, b + 0.75, 0.75, 90); s.note(2, ch[0] - 5, b + 1.5, 0.5, 85)
        s.drum(KICK, b, 105); s.drum(KICK, b + 0.75, 80); s.drum(SNARE, b + 1, 85)
        for i in range(8): s.drum(HHC if i % 2 else SHAKER, b + i * 0.25, 55)
        for i in range(4): s.note(3, ch[(i * 2) % 3] + 24, b + i * 0.5, 0.4, 45)
    mel = "A5:0.5 C6:0.5 F6:1 G6:0.5 F6:0.25 E6:0.25 D6:1 E6:0.5 D6:0.5 B5:1 C6:0.5 E6:0.5 A6:1 F6:0.5 E6:0.5 D6:1 B5:0.5 C6:0.25 D6:0.25 G5:1 C6:0.5 E6:0.5 G6:1 G6:0.5 A6:0.5 C7:1"
    s.melody(0, mel, 0, 100); s.melody(4, mel, 0, 45, oct_shift=-1)
    s.drum(CRASH, 0, 100); s.drum(CRASH, 16, 120); s.drum(KICK, 16, 120)
    s.chord(1, tri('C4', 'maj7'), 16, 3, 85); s.note(2, 'C2', 16, 2, 110)
    s.melody(0, "C6:0.25 E6:0.25 G6:0.25 C7:2", 16, 105)
    s.save(f'{OUT}/1_jingle_B.mid', 2.5)

def jingle_c():  # ブラス・ポップ（明るくて派手め）
    s = Song(160)
    s.program(0, 61); s.program(1, 80); s.program(2, 48); s.program(3, 38); s.program(4, 56)
    prog = [('Bb3','maj'),('F3','maj'),('G3','min'),('Eb3','maj'),('Bb3','maj'),('F3','maj'),('Eb3','maj'),('F3','maj')]
    for bar, (r, k) in enumerate(prog):
        b = bar * 2; ch = tri(r, k)
        s.chord(2, [p + 12 for p in ch], b, 2, 55)
        for i in range(4): s.note(3, ch[0] - 12 + (12 if i % 2 else 0), b + i * 0.5, 0.45, 100)
        s.drum(KICK, b, 115); s.drum(KICK, b + 1, 110); s.drum(SNARE, b + 0.5, 85); s.drum(SNARE, b + 1.5, 90)
        for i in range(4): s.drum(HHO if i % 2 else HHC, b + i * 0.5, 60)
        s.chord(0, [p + 12 for p in ch], b + 0.5, 0.25, 90); s.chord(0, [p + 12 for p in ch], b + 1.5, 0.25, 90)
    mel = "D5:0.5 F5:0.5 Bb5:1 C6:0.5 A5:0.5 F5:1 G5:0.5 Bb5:0.5 D6:1 Eb6:0.5 D6:0.5 C6:1 D6:0.5 C6:0.5 Bb5:0.5 D6:0.5 C6:1.5 A5:0.5 G5:0.5 Bb5:0.5 Eb6:0.5 G6:0.5 F6:2"
    s.melody(4, mel, 0, 100); s.melody(1, mel, 0, 40)
    s.drum(CRASH, 0, 110); s.drum(CRASH, 16, 125); s.drum(KICK, 16, 125)
    for i in range(6): s.drum(TOMH if i < 3 else TOML, 15 + i / 6, 100)
    s.chord(0, [n('Bb4'), n('D5'), n('F5'), n('Bb5')], 16, 2.5, 115); s.note(3, 'Bb1', 16, 2, 115); s.note(4, 'Bb5', 16, 2.5, 110)
    s.save(f'{OUT}/1_jingle_C.mid', 2.5)

# ========== ② 担当パートの解説（しゃべりの下に流す、ループ） ==========
def lofi_a():  # Lo-fi エレピ（ゆったり、少しジャジー）
    s = Song(78)
    s.program(0, 4); s.program(1, 33); s.program(2, 11)
    chords = [tri('F3', 'maj7'), tri('E3', 'm7'), tri('D3', 'm7'), tri('C3', 'maj7')]
    mel_bars = ["R:1 A5:0.5 G5:0.5 E5:2", "R:2 D5:0.5 E5:0.5 G5:1", "R:1 F5:0.5 E5:0.5 C5:1.5 D5:0.5", "E5:3 R:1",
                "R:1 C6:0.5 A5:0.5 G5:2", "R:2 B5:0.5 A5:0.5 E5:1", "R:1 F5:0.5 A5:0.5 G5:1 E5:1", "G5:2 R:2"]
    bars = 16
    for bar in range(bars):
        b = bar * 4; ch = chords[bar % 4]
        sw = 0.08
        s.chord(0, ch, b, 1.9, 58); s.chord(0, ch[1:] + [ch[0] + 12], b + 2.5 + sw, 1.4, 50)
        s.note(1, ch[0] - 12, b, 1.5, 85); s.note(1, ch[0] - 12, b + 1.5 + sw, 0.5, 70); s.note(1, ch[0] - 5, b + 2.5 + sw, 1.4, 75)
        s.drum(KICK, b, 80); s.drum(KICK, b + 1.5 + sw, 60); s.drum(KICK, b + 2.5 + sw, 70); s.drum(RIM, b + 1, 70); s.drum(RIM, b + 3, 70)
        for i in range(8): s.drum(HHC, b + i * 0.5 + (sw if i % 2 else 0), 35 + random.randint(0, 12))
        if bar >= 4 and bar < 12:
            s.melody(2, mel_bars[bar - 4], b, 55)
    s.save(f'{OUT}/2_kaisetsu_A.mid', 3)

def lofi_b():  # ピアノ＋ピチカート（かわいく軽い）
    s = Song(96)
    s.program(0, 0); s.program(1, 45); s.program(2, 32); s.program(3, 9)
    prog = [('F3','maj'),('D3','min'),('Bb2','maj'),('C3','maj')]
    for bar in range(16):
        b = bar * 4; r, k = prog[bar % 4]; ch = tri(r, k)
        s.note(2, ch[0] - 12, b, 0.9, 80); s.note(2, ch[0] - 5, b + 2, 0.9, 75)
        for i in range(4): s.chord(0, [p + 12 for p in ch], b + i + 0.5, 0.4, 45)
        for i, d in enumerate([0, 1, 2, 1, 0, 1, 2, 1]): s.note(1, ch[d] + 12, b + i * 0.5, 0.3, 55)
        s.drum(SHAKER, b + 0.5, 35); s.drum(SHAKER, b + 1.5, 35); s.drum(SHAKER, b + 2.5, 35); s.drum(SHAKER, b + 3.5, 35)
        s.drum(KICK, b, 55); s.drum(KICK, b + 2, 55)
        if bar in (3, 7, 11, 15):
            s.melody(3, "C6:0.5 A5:0.5 F5:0.5 G5:0.5", b + 2, 50)
    s.save(f'{OUT}/2_kaisetsu_B.mid', 3)

def lofi_c():  # ビブラフォン＋ナイロンギター（ボサノバ風、落ち着き）
    s = Song(88)
    s.program(0, 24); s.program(1, 11); s.program(2, 32)
    chords = [tri('D3', 'm7'), tri('G2', '7'), tri('C3', 'maj7'), tri('A2', '7')]
    pattern = [0, 0.75, 1.5, 2.5, 3.25]
    for bar in range(16):
        b = bar * 4; ch = chords[bar % 4]
        for t in pattern: s.chord(0, [p + 12 for p in ch[1:]], b + t, 0.5, 52)
        s.note(2, ch[0] - 12, b, 1.4, 80); s.note(2, ch[0] - 5, b + 1.5, 1.0, 70); s.note(2, ch[0] - 12, b + 2, 1.4, 75); s.note(2, ch[0] - 5, b + 3.5, 0.5, 70)
        s.drum(RIM, b + 0.75, 45); s.drum(RIM, b + 2.5, 45)
        for i in range(8): s.drum(SHAKER, b + i * 0.5, 30 + (10 if i % 2 == 0 else 0))
    mel = ["F5:1.5 E5:0.5 D5:2", "B4:1 D5:1 F5:2", "E5:3 R:1", "C#5:1 E5:1 G5:2",
           "F5:1 A5:1 C6:1.5 A5:0.5", "G5:2 F5:1 D5:1", "E5:4", "R:4"]
    for i in range(8): s.melody(1, mel[i], 16 + i * 4, 58)
    s.save(f'{OUT}/2_kaisetsu_C.mid', 3)

# ========== ③ 討論・結論（緊張感のあるシンセビート） ==========
def tense_a():  # シンセアルペジオ＋四つ打ち
    s = Song(124)
    s.program(0, 81); s.program(1, 38); s.program(2, 50); s.program(3, 84)
    prog = [('A3','min'),('F3','maj'),('D3','min'),('E3','maj')]
    for bar in range(16):
        b = bar * 4; r, k = prog[bar % 4]; ch = tri(r, k)
        s.chord(2, ch, b, 4, 55)
        arp = [ch[0], ch[1], ch[2], ch[0] + 12]
        for i in range(16): s.note(0, arp[i % 4] + 12, b + i * 0.25, 0.2, 50 + (15 if i % 4 == 0 else 0))
        for i in range(8): s.note(1, ch[0] - 12, b + i * 0.5, 0.35, 95 if i % 2 == 0 else 75)
        for i in range(4): s.drum(KICK, b + i, 105)
        if bar >= 2:
            s.drum(CLAP, b + 1, 80); s.drum(CLAP, b + 3, 80)
            for i in range(8): s.drum(HHO if i % 2 else HHC, b + i * 0.5, 50)
        if bar >= 8 and bar % 2 == 0:
            s.melody(3, "A5:1 C6:1 B5:1.5 G#5:0.5" if bar % 4 == 0 else "A5:1 E6:1 D6:2", b, 60)
    s.drum(CRASH, 0, 90); s.drum(CRASH, 32, 100)
    s.save(f'{OUT}/3_touron_A.mid', 3)

def tense_b():  # ストリングスのきざみ＋ティンパニ（シンキングタイム風）
    s = Song(108)
    s.program(0, 48); s.program(1, 47); s.program(2, 42); s.program(3, 89); s.program(4, 112)
    prog = [('D3','min'),('Bb2','maj'),('G2','min'),('A2','maj')]
    for bar in range(16):
        b = bar * 4; r, k = prog[bar % 4]; ch = tri(r, k)
        s.chord(3, [p + 12 for p in ch], b, 4, 45)
        for i in range(16): s.note(0, ch[[0, 2, 1, 2][i % 4]] + 12, b + i * 0.25, 0.15, 60 + (20 if i % 4 == 0 else 0))
        s.note(2, ch[0] - 12, b, 1.8, 80); s.note(2, ch[0] - 12, b + 2, 1.8, 80)
        s.note(1, ch[0] - 12, b, 0.5, 90)
        if bar % 4 == 3:
            for i in range(8): s.note(1, n('A1'), b + 2 + i * 0.25, 0.2, 60 + i * 6)
        for i in range(4): s.drum(WOOD, b + i, 55)  # 時計の音
        s.drum(KICK, b, 90); s.drum(KICK, b + 2.5, 80)
        if bar >= 4: s.drum(SNARE, b + 1, 60); s.drum(SNARE, b + 3, 60)
    s.save(f'{OUT}/3_touron_B.mid', 3)

def tense_c():  # トラップ風（ハーフタイム、ベル＋太いベース）
    s = Song(140)
    s.program(0, 14); s.program(1, 39); s.program(2, 90); s.program(3, 10)
    prog = [('C4','min'),('Ab3','maj'),('Eb3','maj'),('G3','maj')]
    for bar in range(16):
        b = bar * 4; r, k = prog[bar % 4]; ch = tri(r, k)
        s.chord(2, ch, b, 4, 50)
        s.note(1, ch[0] - 24, b, 1.4, 110); s.note(1, ch[0] - 24, b + 1.5, 0.5, 95); s.note(1, ch[0] - 24, b + 2.75, 1.0, 100)
        s.drum(KICK, b, 115); s.drum(KICK, b + 1.5, 100); s.drum(KICK, b + 2.75, 105)
        s.drum(CLAP, b + 2, 95); s.drum(SNARE, b + 2, 70)
        step = 0
        while step < 4:
            if bar % 2 == 1 and 3 <= step < 4: d = 1 / 6
            elif bar % 4 == 2 and 1.5 <= step < 2: d = 0.125
            else: d = 0.5 if bar < 2 else 0.25
            s.drum(HHC, b + step, 55 + random.randint(-8, 8)); step += d
        mb = "C6:0.5 Eb6:0.5 G6:0.5 C6:0.5 Bb5:1 G5:1" if bar % 2 == 0 else "Ab5:0.5 C6:0.5 Eb6:1 D6:1 B5:1"
        if bar >= 2: s.melody(3, mb, b, 60)
    s.save(f'{OUT}/3_touron_C.mid', 3)

# ========== ④ レース・結果発表（オリジナルのファンファーレ） ==========
def fanfare_a():  # 王道ブラスファンファーレ
    s = Song(116)
    s.program(0, 56); s.program(1, 61); s.program(2, 47); s.program(3, 48); s.program(4, 57)
    t = 0
    for i in range(16): s.drum(SNARE, i * 0.125, 50 + i * 4)  # 小さなロール
    t = 2
    s.melody(0, "Bb4:1/3 Bb4:1/3 Bb4:1/3 F5:1.5 D5:0.5 Bb4:1/3 D5:1/3 F5:1/3 Bb5:2 "
                "A5:1/3 G5:1/3 F5:1/3 Eb5:1 G5:1 F5:1/3 Eb5:1/3 D5:1/3 C5:1 F5:1 "
                "Bb4:1/3 D5:1/3 F5:1/3 Bb5:1 C6:1/3 Bb5:1/3 A5:1/3 Bb5:3", t, 110)
    harm = [(2, 'Bb3', 'maj', 3), (5, 'Bb3', 'maj', 3), (8, 'Eb3', 'maj', 2), (10, 'F3', 'maj', 2), (12, 'Bb3', 'maj', 2), (14, 'F3', '7', 1), (15, 'Bb3', 'maj', 3)]
    for st, r, k, d in harm:
        ch = tri(r, k)
        s.chord(1, [p + 12 for p in ch], st, d, 90); s.chord(3, [p + 12 for p in ch] + [ch[0] + 24], st, d, 70)
        s.note(4, ch[0] - 12, st, d, 95); s.note(2, ch[0] - 12 if ch[0] - 12 > 40 else ch[0], st, 0.5, 110)
        s.drum(CRASH, st, 85)
    for i in range(12): s.note(2, n('F2'), 14 + i / 12, 0.1, 70 + i * 4)
    s.drum(CRASH, 15, 125); s.drum(KICK, 15, 120)
    s.save(f'{OUT}/4_fanfare_A.mid', 3)

def fanfare_b():  # ドラムロール→ジャン！（結果発表）
    s = Song(120)
    s.program(0, 56); s.program(1, 61); s.program(2, 47); s.program(3, 48)
    for i in range(48): s.drum(SNARE, i * 1/12, 40 + int(i * 1.5))  # 約2秒のロール
    for i in range(48): s.note(2, n('G2'), i * 1/12, 0.08, 40 + int(i * 1.2))
    s.drum(CRASH, 4, 127); s.drum(KICK, 4, 127)
    ch = [n('C4'), n('E4'), n('G4'), n('C5'), n('E5'), n('G5')]
    s.chord(1, ch[:4], 4, 0.4, 115); s.chord(0, ch[3:], 4, 0.4, 115)
    s.chord(1, ch[:4], 4.75, 0.25, 110); s.chord(0, ch[3:], 4.75, 0.25, 110)
    s.chord(1, ch[:4], 5, 3, 120); s.chord(0, ch[3:] + [n('C6')], 5, 3, 120); s.chord(3, ch, 5, 3, 90)
    s.note(2, 'C2', 5, 0.5, 120); s.drum(CRASH, 5, 120)
    s.save(f'{OUT}/4_fanfare_B.mid', 3)

def fanfare_c():  # ピコピコ勝利ファンファーレ（かわいい系）
    s = Song(150)
    s.program(0, 80); s.program(1, 81); s.program(2, 38); s.program(3, 9)
    s.melody(0, "C5:1/3 E5:1/3 G5:1/3 C6:1 G5:0.5 C6:0.5 E6:2 D6:1/3 E6:1/3 F6:1/3 G6:1 E6:0.5 G6:0.5 C7:3", 0, 105)
    s.melody(1, "E4:1/3 G4:1/3 C5:1/3 E5:1 C5:0.5 E5:0.5 G5:2 B5:1/3 C6:1/3 D6:1/3 E6:1 C6:0.5 E6:0.5 G6:3", 0, 55)
    for st, r in [(1, 'C3'), (2, 'C3'), (3, 'C3'), (5, 'G2'), (6, 'G2'), (7, 'G2'), (9, 'C3')]:
        s.note(2, r, st, 0.4, 100); s.drum(KICK, st, 100); s.drum(HHC, st + 0.5, 60)
    s.drum(SNARE, 2, 80); s.drum(SNARE, 6, 80); s.drum(CRASH, 1, 100); s.drum(CRASH, 9, 115)
    s.melody(3, "C7:0.25 E7:0.25 G7:0.25 C8:1", 9, 80)
    s.save(f'{OUT}/4_fanfare_C.mid', 2.5)

# ========== ⑤ 外れた時のズッコケ効果音 ==========
def miss_a():  # トロンボーンの「ぽわ〜ん…」
    s = Song(100)
    s.program(0, 57); s.cc(0, 0, 101, 0); s.cc(0, 0, 100, 0); s.cc(0, 0, 6, 2)  # ベンド幅±2
    s.melody(0, "Bb3:0.75 A3:0.75 Ab3:0.75 G3:2.5", 0, 105)
    for i in range(40):
        import math
        s.bend(0, 2.4 + i * 0.05, int(1400 * math.sin(i * 0.9)))
    s.bend(0, 4.7, 0)
    s.save(f'{OUT}/5_zukkoke_A.mid', 1.5)

def miss_c():  # ピコピコ下がり音＋ドテッ
    s = Song(150)
    s.program(0, 80); s.program(1, 47)
    t = 0
    for p in ['C6', 'B5', 'Bb5', 'A5', 'Ab5', 'G5', 'F#5', 'F5', 'E5', 'Eb5', 'D5', 'C#5', 'C5']:
        s.note(0, p, t, 0.12, 95); t += 0.125
    s.note(0, 'C4', t + 0.25, 0.25, 95); s.note(0, 'C3', t + 0.6, 0.6, 100)
    s.note(1, 'C2', t + 0.6, 1, 120); s.drum(KICK, t + 0.6, 127); s.drum(CRASH, t + 0.6, 70)
    s.save(f'{OUT}/5_zukkoke_C.mid', 1.5)

for f in [jingle_a, jingle_b, jingle_c, lofi_a, lofi_b, lofi_c, tense_a, tense_b, tense_c, fanfare_a, fanfare_b, fanfare_c, miss_a, miss_c]:
    f()
print('ok')
