import { useState, useEffect, useRef } from 'react';
import { VerboseLoadingGenerator } from '@/utils/verboseLoading';

export function useVerboseLoading() {
  const [currentMessage, setCurrentMessage] = useState<string>('Processing your request...');
  const generatorRef = useRef<VerboseLoadingGenerator | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const usingExternalUpdates = useRef<boolean>(false);

  useEffect(() => {
    // Initialize generator
    if (!generatorRef.current) {
      generatorRef.current = new VerboseLoadingGenerator();
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, []);

  const start = () => {
    setIsLoading(true);
    usingExternalUpdates.current = false; // Start with automatic messages
    if (generatorRef.current) {
      generatorRef.current.forceReset();
      setCurrentMessage(generatorRef.current.getCurrentMessage());
    }

    // Set up interval to update message only if not using external updates
    intervalRef.current = setInterval(() => {
      if (generatorRef.current && !usingExternalUpdates.current) {
        setCurrentMessage(generatorRef.current.getCurrentMessage());
      }
    }, 100); // Update every 100ms for smooth transitions
  };

  const stop = () => {
    setIsLoading(false);
    usingExternalUpdates.current = false;
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
    }
  };

  const setProgressMessage = (message: string) => {
    usingExternalUpdates.current = true; // Mark that we're using external updates
    setCurrentMessage(message);
  };

  const reset = () => {
    usingExternalUpdates.current = false;
    if (generatorRef.current) {
      generatorRef.current.forceReset();
      setCurrentMessage(generatorRef.current.getCurrentMessage());
    }
  };

  return { currentMessage, start, stop, setProgressMessage, isLoading };
}
