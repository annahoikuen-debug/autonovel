/**
 * AutoNovel 商業LP - メインページ
 *
 * ファイル: frontend/src/pages/lp/LpPage.tsx
 *
 * 役割: すべての LP セクションを統合したトップページ。
 * LpLayout で Header + main + Footer をラップする。
 */

import React from 'react';
import { LpLayout } from '../../components/lp/LpLayout';
import { LpHead } from '../../components/lp/LpHead';
import { HeroSection } from '../../components/lp/HeroSection';
import { EntryPointsSection } from '../../components/lp/EntryPointsSection';
import { FeaturesSection } from '../../components/lp/FeaturesSection';
import { PricingSection } from '../../components/lp/PricingSection';
import { TestimonialsSection } from '../../components/lp/TestimonialsSection';
import { FaqSection } from '../../components/lp/FaqSection';
import { FinalCtaSection } from '../../components/lp/FinalCtaSection';

export const LpPage: React.FC = () => {
  return (
    <div data-testid="lp-page">
      <LpHead />
      <LpLayout>
        <HeroSection />
        <EntryPointsSection />
        <FeaturesSection />
        <PricingSection />
        <TestimonialsSection />
        <FaqSection />
        <FinalCtaSection />
      </LpLayout>
    </div>
  );
};

export default LpPage;