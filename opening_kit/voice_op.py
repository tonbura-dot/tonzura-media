# オープニングのコール音声（eli4/voice4_core.py と同じ声・設定）
import wave, io, sys
from voicevox_core.blocking import Onnxruntime, OpenJtalk, Synthesizer, VoiceModelFile
VV='/mnt/project-files/video/voicevox'
SPK={'ロゼ':16,'ミレイ':14,'ソラ':20,'ララン':8}
VVM={16:'/tmp/vvm/2.vvm',14:'/tmp/vvm/1.vvm',20:f'{VV}/vvms/15.vvm',8:'/tmp/vvm/0.vvm'}
ort=Onnxruntime.load_once(filename=f'{VV}/voicevox_onnxruntime-linux-x64-1.17.3/lib/libvoicevox_onnxruntime.so.1.17.3')
sy=Synthesizer(ort,OpenJtalk(f'{VV}/open_jtalk_dic_utf_8-1.11'))
for p in set(VVM.values()):
    with VoiceModelFile.open(p) as m: sy.load_voice_model(m)
LINES={'sora':('ソラ','いちかく、ソラ！',1.3,1.05),'laran':('ララン','にかく、ララン！',1.25,1.1),
       'mirei':('ミレイ','さんかく、ミレイ。',1.25,1.0),'rose':('ロゼ','よんかく、ロゼ。',1.3,1.0)}
for who in SPK: LINES['call_'+who]=(who,'よんかくめがみ！',1.15,1.12)
for k,(who,t,sp,pitch) in LINES.items():
    s=SPK[who]; q=sy.create_audio_query(t,s); q.speed_scale=sp; q.intonation_scale=1.4
    q.pitch_scale=(pitch-1)*0.1; q.volume_scale=1.3; q.pre_phoneme_length=0.02; q.post_phoneme_length=0.1; q.output_sampling_rate=48000
    open(f'voice/{k}.wav','wb').write(sy.synthesis(q,s))
    print(k)
