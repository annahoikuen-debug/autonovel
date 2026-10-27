import React, { useEffect, useState } from 'react';

export interface MissingBeat {
  key: string;
  label: string;
  present: boolean;
  expected_phase: number;
}

export interface StructureValidationResult {
  pattern_key?: string;
  resolved_pattern_key?: string;
  structure_key?: string;
  is_healthy?: boolean;
  alignment?: number;
  missing_beats?: MissingBeat[];
  climax?: { ok: boolean; reason?: string; climax_phase?: number | null };
  pacing?: { ok: boolean; reason?: string; skew?: number };
  problems?: Array<string | { key: string; reason: string }>;
}

export interface BeatSheetViewerProps {
  bookId?: number;
  patternKey?: string;
  onSelectBeat?: (beatNumber: number) => void;
}

export const BeatSheetViewer: React.FC<BeatSheetViewerProps> = ({
  bookId = 1,
  patternKey = 'exile_rise',
  onSelectBeat,
}) => {
  const [validation, setValidation] = useState<StructureValidationResult | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);
    setError(null);

    const url = `/api/structure/books/${bookId}/validate?pattern=${encodeURIComponent(patternKey)}`;
    fetch(url)
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(`検証APIエラー: ${res.status}`);
        }
        return res.json();
      })
      .then((data: StructureValidationResult) => {
        if (isMounted) {
          setValidation(data);
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (isMounted) {
          setError(err instanceof Error ? err.message : '構造検証に失敗しました');
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [bookId, patternKey]);

  return (
    <div className="beat-sheet-viewer p-5 bg-slate-900 text-white rounded-xl border border-slate-800 shadow-md">
      <div className="flex items-center justify-between mb-4 border-b border-slate-800 pb-3">
        <div>
          <h2 className="text-xl font-bold text-sky-400">📊 物語構成充足度・ビートシート検証</h2>
          <p className="text-xs text-slate-400 mt-1">
            STORY_SPINE テンプレートパターンに照らしたビート配置・クライマックス位置・テンション推移の自動検証
          </p>
        </div>
        {validation && (
          <div className="flex items-center gap-2">
            {validation.alignment !== undefined && (
              <span className="px-3 py-1 bg-sky-950 border border-sky-700 text-sky-300 rounded-full text-xs font-semibold">
                充足度: {(validation.alignment * 100).toFixed(1)}%
              </span>
            )}
            <span
              className={`px-3 py-1 rounded-full text-xs font-semibold ${
                validation.is_healthy
                  ? 'bg-emerald-950 text-emerald-300 border border-emerald-700'
                  : 'bg-amber-950 text-amber-300 border border-amber-700'
              }`}
            >
              {validation.is_healthy ? '✅ 構造健全' : '⚠️ 改善推奨'}
            </span>
          </div>
        )}
      </div>

      {isLoading && (
        <div className="text-center py-6 text-slate-400 text-sm animate-pulse">
          構造充足度を解析中...
        </div>
      )}

      {error && !isLoading && (
        <div className="p-3 bg-red-950/60 border border-red-800 rounded text-red-300 text-sm mb-4">
          {error}
        </div>
      )}

      {validation && !isLoading && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="p-3 bg-slate-800/60 rounded-lg border border-slate-700">
              <span className="text-xs text-slate-400">適用パターン</span>
              <div className="font-semibold text-sky-300 mt-0.5">
                {validation.resolved_pattern_key || validation.pattern_key || patternKey}
              </div>
            </div>
            <div className="p-3 bg-slate-800/60 rounded-lg border border-slate-700">
              <span className="text-xs text-slate-400">クライマックス位置</span>
              <div
                className={`font-semibold mt-0.5 ${
                  validation.climax?.ok ? 'text-emerald-400' : 'text-amber-400'
                }`}
              >
                {validation.climax?.ok ? '適切 (終盤到達)' : '再調整推奨'}
              </div>
            </div>
            <div className="p-3 bg-slate-800/60 rounded-lg border border-slate-700">
              <span className="text-xs text-slate-400">ペーシング・推移</span>
              <div
                className={`font-semibold mt-0.5 ${
                  validation.pacing?.ok ? 'text-emerald-400' : 'text-amber-400'
                }`}
              >
                {validation.pacing?.ok ? '均整 (良好)' : '山場集中あり'}
              </div>
            </div>
          </div>

          {/* 欠落ビート・未充足ビート */}
          <div className="p-4 bg-slate-800/40 rounded-lg border border-slate-800">
            <h3 className="text-sm font-semibold mb-2 text-slate-200">
              🎯 必須ビートの充足状況
            </h3>
            {validation.missing_beats && validation.missing_beats.length > 0 ? (
              <div>
                <p className="text-xs text-amber-300 mb-2">
                  以下のビートがプロット上で検出されていないか、推奨区間に配置されていません:
                </p>
                <div className="flex flex-wrap gap-2">
                  {validation.missing_beats.map((beat) => (
                    <span
                      key={beat.key}
                      className="px-2.5 py-1 bg-amber-950/70 border border-amber-700/60 text-amber-200 text-xs rounded font-mono"
                    >
                      {beat.label} (期待: {(beat.expected_phase * 100).toFixed(0)}%)
                    </span>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-xs text-emerald-400">
                🎉 すべての必須ビート（発端・中点反転・クライマックス等）が正常に配置されています。
              </p>
            )}
          </div>

          {/* 課題リスト（あれば） */}
          {validation.problems && validation.problems.length > 0 && (
            <div className="p-3 bg-amber-950/40 border border-amber-800/60 rounded-lg">
              <span className="text-xs font-semibold text-amber-300">検出された構造上の課題:</span>
              <ul className="text-xs text-amber-200 mt-1 list-disc list-inside space-y-0.5">
                {validation.problems.map((p, idx) => (
                  <li key={idx}>
                    {typeof p === 'string' ? p : `${p.key}: ${p.reason}`}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default BeatSheetViewer;