import React, { createContext, useContext, useEffect, useState } from 'react';
import type { ManuscriptTargetPreset } from '../types/manuscript';
import { fetchLengthProfiles, toManuscriptPresets, MANUSCRIPT_PRESETS } from '../constants/manuscript';

interface LengthPresetContextValue {
  presets: ManuscriptTargetPreset[];
  isLoading: boolean;
}

const LengthPresetContext = createContext<LengthPresetContextValue>({
  presets: MANUSCRIPT_PRESETS,
  isLoading: false,
});

export const LengthPresetProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [presets, setPresets] = useState<ManuscriptTargetPreset[]>(MANUSCRIPT_PRESETS);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);
    fetchLengthProfiles()
      .then((profiles) => {
        if (isMounted && profiles.length > 0) {
          setPresets(toManuscriptPresets(profiles));
        }
      })
      .catch(() => {
        // Fallback to MANUSCRIPT_PRESETS already set
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <LengthPresetContext.Provider value={{ presets, isLoading }}>
      {children}
    </LengthPresetContext.Provider>
  );
};

export const useLengthPresets = (): LengthPresetContextValue => {
  return useContext(LengthPresetContext);
};
