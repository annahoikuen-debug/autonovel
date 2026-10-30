/**
 * AutoNovel 商業LP - 導入事例・ユーザーの声セクション
 *
 * ファイル: frontend/src/components/lp/TestimonialsSection.tsx
 *
 * 役割: 実際のユーザー（または仮の事例）の声を掲載し、ソーシャルプルーフによる信頼構築を行う。
 */

import React from 'react';

interface Testimonial {
  id: number;
  name: string;
  role: string;
  genre: string;
  rating: number;
  content: string;
  avatar: string;
}

const TESTIMONIALS: Testimonial[] = [
  {
    id: 1,
    name: '佐藤健太',
    role: 'ライトノベル作家',
    genre: 'ファンタジー',
    rating: 5,
    content:
      'プロット作成が劇的に楽になりました。8 オーディターの矛盾チェックがあるおかげで、長編でも設定のブレが気にならなくなりました。',
    avatar: 'https://ui-avatars.com/api/?name=Sato+Kenta&background=22d3ee&color=fff',
  },
  {
    id: 2,
    name: '鈴木花子',
    role: 'Web 小説家',
    genre: 'ラブコメ',
    rating: 4,
    content:
      'リアルタイム速筆でアイデアがどんどん形になります。なろう形式への出力もすぐできて、投稿までのスピードが上がりました。',
    avatar: 'https://ui-avatars.com/api/?name=Suzuki+Hanako&background=a855f7&color=fff',
  },
  {
    id: 3,
    name: '田中次郎',
    role: 'SF 作家',
    genre: 'SF',
    rating: 5,
    content:
      '相関図ビジュアル化でキャラクター関係を一目で把握できます。EPUB 出力ですぐにカクヨムに投稿できたのも助かりました。',
    avatar: 'https://ui-avatars.com/api/?name=Tanaka+Jiro&background=06b6d4&color=fff',
  },
];

export const TestimonialsSection: React.FC = () => {
  return (
    <section
      id="lp-testimonials-section"
      className="py-16 px-4 sm:py-24 sm:px-6 lg:py-32 lg:px-8"
      data-testid="lp-testimonials-section"
    >
      <div className="max-w-7xl mx-auto">
        {/* セクション見出し */}
        <div className="text-center mb-16" data-testid="lp-testimonials-header">
          <h2
            className="text-3xl sm:text-4xl font-bold text-brand-text mb-4"
            data-testid="lp-testimonials-title"
          >
            作家・クリエイターの声
          </h2>
          <p
            className="text-lg text-brand-textMuted max-w-2xl mx-auto leading-relaxed"
            data-testid="lp-testimonials-desc"
          >
            AutoNovel をご利用いただいているクリエイターの感想です。
          </p>
        </div>

        {/* ソーシャルプルーフ */}
        <div
          className="flex items-center justify-center gap-6 text-sm text-brand-textMuted mb-16"
          data-testid="lp-social-proof"
        >
          <span data-testid="lp-social-proof-novels">
            累計生成小説数: 10,000 件以上
          </span>
          <span aria-hidden="true">·</span>
          <span data-testid="lp-social-proof-users">
            登録ユーザー数: 5,000 名以上
          </span>
        </div>

        {/* 事例カードグリッド */}
        <div
          className="grid grid-cols-1 md:grid-cols-3 gap-6 sm:gap-8 lg:gap-12"
          data-testid="lp-testimonials-grid"
        >
          {TESTIMONIALS.map((testimonial) => (
            <div
              key={testimonial.id}
              className="
                p-6 sm:p-8
                bg-brand-surface
                border border-brand-border
                rounded-xl
                flex flex-col
                h-full
              "
              data-testid={`lp-testimonial-card-${testimonial.id}`}
            >
              {/* ヘッダー: アバター・名前・ジャンル */}
              <div className="flex items-center gap-3 mb-4" data-testid={`lp-testimonial-header-${testimonial.id}`}>
                <img
                  src={testimonial.avatar}
                  alt={`${testimonial.name} のアバター`}
                  className="w-10 h-10 rounded-full object-cover"
                  loading="lazy"
                  data-testid={`lp-testimonial-avatar-${testimonial.id}`}
                />
                <div>
                  <h4
                    className="text-sm font-semibold text-brand-text"
                    data-testid={`lp-testimonial-name-${testimonial.id}`}
                  >
                    {testimonial.name}
                  </h4>
                  <p
                    className="text-xs text-brand-textMuted"
                    data-testid={`lp-testimonial-genre-${testimonial.id}`}
                  >
                    {testimonial.genre}
                  </p>
                </div>
              </div>

              {/* 評価スター */}
              <div className="flex gap-1 mb-4" data-testid={`lp-testimonial-rating-${testimonial.id}`}>
                {[1, 2, 3, 4, 5].map((star) => (
                  <span
                    key={star}
                    className="text-xs"
                    data-testid={`lp-testimonial-star-${testimonial.id}-${star}`}
                  >
                    {star <= testimonial.rating ? '★' : '☆'}
                  </span>
                ))}
              </div>

              {/* 感想文 */}
              <p
                className="text-sm text-brand-textMuted leading-relaxed mb-6 flex-grow"
                data-testid={`lp-testimonial-content-${testimonial.id}`}
              >
                「{testimonial.content}」
              </p>

              {/* ロール */}
              <p
                className="text-xs text-brand-accent font-medium"
                data-testid={`lp-testimonial-role-${testimonial.id}`}
              >
                {testimonial.role}
              </p>
            </div>
          ))}
        </div>

        {/* 補足：事例は仮の内容 */}
        <p
          className="text-xs text-brand-textMuted text-center mt-8"
          data-testid="lp-testimonials-disclaimer"
        >
          ※事例は仮の内容です。実際のユーザーの声に差し替えます。
        </p>
      </div>
    </section>
  );
};

export default TestimonialsSection;