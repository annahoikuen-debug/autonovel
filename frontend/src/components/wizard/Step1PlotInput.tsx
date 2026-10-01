import React, { useEffect, useState } from 'react';
import { expandBeats, ExpandBeatsRequest, BeatItem } from '../../api/wizard';
import { GENRE_OPTIONS, GenreOption } from '../../constants/genres';

interface Step1Props {
  onNext: (data: {
    title: string;
    genre: string;
    synopsis: string;
    targetChapters: number;
    cheatScale: number;
    growthCurve: string;
    systemAssist: number;
    costSeverity: number;
    beats: BeatItem[];
    patternKey?: string;
    lengthKey?: string;
    marketKey?: string;
  }) => void;
}

const DEFAULT_GROWTH_CURVES = [
  '最初からカンスト(無双)',
  '徐々に成長(王道)',
  '条件付き最強(ピーキー)',
];

export const Step1PlotInput: React.FC<Step1Props> = ({ onNext }) => {
  const [title, setTitle] = useState('');
  const [genre, setGenre] = useState('HighFantasy');
  const [synopsis, setSynopsis] = useState('');
  const [targetChapters, setTargetChapters] = useState(20);
  const [cheatScale, setCheatScale] = useState(4);
  const [growthCurve, setGrowthCurve] = useState('最初からカンスト(無双)');
  const [systemAssist, setSystemAssist] = useState(70);
  const [costSeverity, setCostSeverity] = useState(2);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // STORY_SPINE 連携
  const [cards, setCards] = useState<any[]>([]);
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
  const [patternKey, setPatternKey] = useState<string>('');
  const [lengthKey, setLengthKey] = useState<string>('');
  const [marketKey, setMarketKey] = useState<string>('');
  const [growthCurves, setGrowthCurves] = useState<string[]>(DEFAULT_GROWTH_CURVES);
  const [genreOptions, setGenreOptions] = useState<GenreOption[]>(GENRE_OPTIONS);

  useEffect(() => {
    let isMounted = true;
    fetch('/api/config/planning_options')
      .then((res) => res.json())
      .then((data) => {
        if (!isMounted) return;
        if (data.growth_curves && Array.isArray(data.growth_curves) && data.growth_curves.length > 0) {
          setGrowthCurves(data.growth_curves);
          setGrowthCurve(data.growth_curves[0]);
        }
        if (data.genres) {
          const raw = Array.isArray(data.genres) ? data.genres : Object.values(data.genres);
          const mapped = raw.map((g: any) => ({
            value: g.key || g.value,
            label: g.label || g.name || g.key,
            presetKey: g.preset_key ?? null,
          }));
          if (mapped.length > 0) setGenreOptions(mapped);
        }
        if (data.cards) {
          const rawCards = Array.isArray(data.cards) ? data.cards : Object.values(data.cards);
          setCards(rawCards);
        }
      })
      .catch(() => {});
    return () => {
      isMounted = false;
    };
  }, []);

  const handleSelectCard = (card: any) => {
    const cid = card.card_id ?? card.id;
    setSelectedCardId(cid ?? null);
    setPatternKey(card.pattern || '');
    setLengthKey(card.length || '');
    setMarketKey(card.market || '');

    if (card.length === 'web_volume') {
      setTargetChapters(40);
    } else if (card.length === 'short') {
      setTargetChapters(2);
    } else if (card.length === 'single_volume') {
      setTargetChapters(18);
    }
  };

  const validateForm = (): boolean => {
    if (!title.trim()) {
      setError('作品タイトルを入力してください');
      return false;
    }
    if (!synopsis.trim()) {
      setError('あらすじ・コアアイデアを入力してください');
      return false;
    }
    if (cheatScale < 1 || cheatScale > 5) {
      setError('チート度は1〜5で設定してください');
      return false;
    }
    if (costSeverity < 1 || costSeverity > 5) {
      setError('代償・世界リスク過酷度は1〜5で設定してください');
      return false;
    }
    if (systemAssist < 0 || systemAssist > 100) {
      setError('システム支援度は0〜100で設定してください');
      return false;
    }
    if (targetChapters < 1 || targetChapters > 100) {
      setError('目標話数は1〜100で設定してください');
      return false;
    }
    setError(null);
    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateForm()) return;

    setIsLoading(true);
    setError(null);

    try {
      const request: ExpandBeatsRequest = {
        title,
        genre,
        synopsis,
        target_chapters: targetChapters,
        cheat_scale: cheatScale,
        growth_curve: growthCurve,
        system_assist: systemAssist,
        cost_severity: costSeverity,
        pattern_key: patternKey,
        length_key: lengthKey,
        market_key: marketKey,
      };

      const beats = await expandBeats(request);

      onNext({
        title,
        genre,
        synopsis,
        targetChapters,
        cheatScale,
        growthCurve,
        systemAssist,
        costSeverity,
        beats,
        patternKey,
        lengthKey,
        marketKey,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'ビート生成に失敗しました';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="wizard-step step1-container p-6 bg-slate-900 text-white rounded-xl shadow-lg">
      {/* 見出しは既存導線との後方互換のため `Step 1: ...` のまま据え置く */}
      <h2 className="text-2xl font-bold mb-2 text-sky-400">Step 1: 企画アイデアと成長曲線の設計</h2>
      <p className="text-slate-400 mb-6 text-sm">
        主人公にどの程度の「 유리」を与えるか、どう成長させていくかを決めます。
        <strong className="text-slate-200">
          迷ったら上の「構造テンプレート」を1つ選ぶだけで設定が入ります。
        </strong>
      </p>

      {/* 構造テンプレートカード一覧 */}
      {cards.length > 0 && (
        <div className="mb-4">
          <label className="block text-sm font-medium mb-1 text-slate-300">🎯 構造テンプレートカード（選択すると構成が自動セットされます）</label>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2 max-h-40 overflow-y-auto p-1">
            {cards.map((card) => {
              const cid = card.card_id ?? card.id;
              const isSelected = selectedCardId === cid;
              return (
                <div
                  key={cid}
                  onClick={() => handleSelectCard(card)}
                  className={`p-2 rounded border cursor-pointer transition-colors text-xs ${
                    isSelected ? 'border-sky-400 bg-sky-950/60' : 'border-slate-700 bg-slate-800/40 hover:bg-slate-800'
                  }`}
                >
                  <div className="font-semibold">{card.label}</div>
                  <div className="text-slate-400 text-[10px] mt-0.5">{card.length} / {card.market}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="p-3 bg-red-900/50 border border-red-700 rounded-lg text-red-200 text-sm">
            {error}
          </div>
        )}

        <div>
          <label className="block text-sm font-medium mb-1">作品タイトル</label>
          <input
            type="text"
            className="w-full p-2.5 rounded bg-slate-800 border border-slate-700 text-white focus:outline-none focus:border-sky-500"
            placeholder="例: 魔王の娘に転生した鍛冶屋の日常"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={isLoading}
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">ジャンル</label>
            <select
              className="w-full p-2.5 rounded bg-slate-800 border border-slate-700 text-white"
              value={genre}
              onChange={(e) => setGenre(e.target.value)}
              disabled={isLoading}
            >
              {genreOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">成長曲線モデル</label>
            <select
              className="w-full p-2.5 rounded bg-slate-800 border border-slate-700 text-white"
              value={growthCurve}
              onChange={(e) => setGrowthCurve(e.target.value)}
              disabled={isLoading}
            >
              {growthCurves.map((curve) => (
                <option key={curve} value={curve}>
                  {curve}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/*
          スライダーには両端の説明と `aria-valuetext` を付けることで、
          「いま何を調整しているのか」を数値を見なくても分かるようにする。
        */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="cheat-scale" className="block text-sm font-medium mb-1">
              チート度: {cheatScale} / 5
            </label>
            <input
              id="cheat-scale"
              type="range"
              min={1}
              max={5}
              value={cheatScale}
              onChange={(e) => setCheatScale(Number(e.target.value))}
              className="w-full accent-sky-500"
              disabled={isLoading}
              aria-describedby="cheat-scale-help"
              aria-valuetext={`${cheatScale}。${cheatScale <= 2 ? '主人公は一般人' : cheatScale <= 3 ? '少し頼れる' : cheatScale <= 4 ? 'かなり有利' : '無敵に近い'}`}
            />
            <p id="cheat-scale-help" className="text-xs text-slate-400 mt-1">
              1: 主人公も一般人 / 3: 少し頼れる / 5: 無敵に近い
            </p>
          </div>
          <div>
            <label htmlFor="cost-severity" className="block text-sm font-medium mb-1">
              代償・世界の過酷さ: {costSeverity} / 5
            </label>
            <input
              id="cost-severity"
              type="range"
              min={1}
              max={5}
              value={costSeverity}
              onChange={(e) => setCostSeverity(Number(e.target.value))}
              className="w-full accent-amber-500"
              disabled={isLoading}
              aria-describedby="cost-severity-help"
              aria-valuetext={`${costSeverity}。${costSeverity <= 2 ? '穏やか' : costSeverity <= 3 ? 'ある程度の闇' : '容赦ない世界'}`}
            />
            <p id="cost-severity-help" className="text-xs text-slate-400 mt-1">
              1: 穏やか / 3: ある程度の闇 / 5: 容赦ない世界
            </p>
          </div>
        </div>

        <div>
          <label htmlFor="system-assist" className="block text-sm font-medium mb-1">
            主人公をやさしく助ける割合: {systemAssist}%
          </label>
          <input
            id="system-assist"
            type="range"
            min={0}
            max={100}
            value={systemAssist}
            onChange={(e) => setSystemAssist(Number(e.target.value))}
            className="w-full accent-emerald-500"
            disabled={isLoading}
            aria-describedby="system-assist-help"
            aria-valuetext={`${systemAssist}%。${systemAssist <= 30 ? 'ほぼ独力でなんとか' : systemAssist <= 70 ? '助けがほどほどにある' : '常に手を差し伸べられる'}`}
          />
          <p id="system-assist-help" className="text-xs text-slate-400 mt-1">
            0: 主人公が独力でなんとか / 100: 常に手を差し伸べられる
          </p>
        </div>

        <div>
          <label htmlFor="target-chapters" className="block text-sm font-medium mb-1">
            目標話数: {targetChapters} 話
          </label>
          <input
            id="target-chapters"
            type="range"
            min={1}
            max={100}
            value={targetChapters}
            onChange={(e) => setTargetChapters(Number(e.target.value))}
            className="w-full accent-purple-500"
            disabled={isLoading}
            aria-valuetext={`${targetChapters} 話`}
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">あらすじ・コアアイデア</label>
          <textarea
            rows={4}
            className="w-full p-2.5 rounded bg-slate-800 border border-slate-700 text-white focus:outline-none focus:border-sky-500"
            placeholder="主人公の特技、最初の事件、物語のゴールなどを自由に記述"
            value={synopsis}
            onChange={(e) => setSynopsis(e.target.value)}
            disabled={isLoading}
          />
        </div>

        <button
          type="submit"
          disabled={isLoading}
          className="w-full py-3 bg-sky-600 hover:bg-sky-500 disabled:bg-sky-900 disabled:cursor-not-allowed rounded font-semibold text-white transition-colors"
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              AIアイデア生成中...
            </span>
          ) : (
            '次へ: 五感ビートとクリフハンガー構成を自動設計する →'
          )}
        </button>
      </form>
    </div>
  );
};