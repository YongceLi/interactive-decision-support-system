import { useState, useEffect, useRef } from 'react';
import { VerboseLoadingGenerator } from '@/utils/verboseLoading';

export function useVerboseLoading(userInput?: string) {
  const [currentMessage, setCurrentMessage] = useState<string>('Processing your request...');
  const generatorRef = useRef<VerboseLoadingGenerator | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    // Initialize generator
    if (!generatorRef.current) {
      generatorRef.current = new VerboseLoadingGenerator();
    }

    // Always reset and start fresh when user input changes
    if (generatorRef.current) {
      generatorRef.current.forceReset();
      setCurrentMessage(generatorRef.current.getCurrentMessage());
    }

    // Set up interval to update message
    intervalRef.current = setInterval(() => {
      if (generatorRef.current) {
        setCurrentMessage(generatorRef.current.getCurrentMessage());
      }
    }, 100); // Update every 100ms for smooth transitions

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [userInput]);

  const reset = () => {
    if (generatorRef.current) {
      generatorRef.current.forceReset();
      setCurrentMessage(generatorRef.current.getCurrentMessage());
    }
  };

  return { currentMessage, reset };
}
