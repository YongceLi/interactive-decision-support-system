/**
 * Verbose loading messages that show what the agent is doing step by step
 */

export interface LoadingStep {
  id: string;
  message: string;
  duration: number; // How long to show this step (ms)
  isProgress?: boolean; // If true, shows progress counter
}

export class VerboseLoadingGenerator {
  private steps: LoadingStep[] = [
    { id: 'analyzing', message: 'Analyzing your request', duration: 3000 },
    { id: 'fetching', message: 'Fetching product details', duration: 3000 },
    { id: 'filtering', message: 'Filtering recommendations', duration: 3000 },
    { id: 'ranking', message: 'Ranking best matches', duration: 3000 },
    { id: 'preparing', message: 'Preparing your results', duration: 3000 }
  ];

  private currentStepIndex = 0;
  private startTime = 0;
  private currentStep: LoadingStep | null = null;
  private progressCount = 0;

  constructor() {
    this.reset();
  }

  reset(): void {
    this.currentStepIndex = 0;
    this.startTime = Date.now();
    this.currentStep = this.steps[0];
    this.progressCount = 0;
  }

  getCurrentMessage(): string {
    if (!this.currentStep) {
      return 'Processing your request...';
    }

    const elapsed = Date.now() - this.startTime;
    
    // Check if we should move to the next step
    if (elapsed >= this.currentStep.duration && this.currentStepIndex < this.steps.length - 1) {
      this.currentStepIndex++;
      this.currentStep = this.steps[this.currentStepIndex];
      this.startTime = Date.now();
      
      // Reset progress counter for new step
      this.progressCount = 0;
    }

    // Add progress counter for certain steps
    if (this.currentStep.isProgress) {
      this.progressCount++;
      return `${this.currentStep.message} (${this.progressCount})`;
    }

    return this.currentStep.message;
  }

  isComplete(): boolean {
    const elapsed = Date.now() - this.startTime;
    return this.currentStepIndex >= this.steps.length - 1 && 
           elapsed >= (this.currentStep?.duration || 0);
  }

  // Force reset to first step
  forceReset(): void {
    this.currentStepIndex = 0;
    this.startTime = Date.now();
    this.currentStep = this.steps[0];
    this.progressCount = 0;
  }

  // Get contextual message based on user input
  static getContextualMessage(userInput: string): string {
    const input = userInput.toLowerCase();
    
    if (input.includes('budget') || input.includes('price') || input.includes('$') || input.includes('cost')) {
      return 'Analyzing your budget requirements';
    }
    
    if (input.includes('location') || input.includes('city') || input.includes('state')) {
      return 'Processing location preferences';
    }
    
    if (input.includes('brand') || input.includes('make') || input.includes('model')) {
      return 'Filtering by brand preferences';
    }
    
    if (input.includes('compare') || input.includes('vs') || input.includes('difference')) {
      return 'Preparing comparison analysis';
    }
    
    if (input.includes('tell me more') || input.includes('details') || input.includes('about')) {
      return 'Gathering detailed information';
    }
    
    // Default to first step
    return 'Analyzing your request';
  }

  // Get a random contextual message for variety
  static getRandomMessage(): string {
    const messages = [
      'Analyzing your request',
      'Understanding your preferences',
      'Searching for the best options',
      'Processing your criteria',
      'Finding perfect matches',
      'Optimizing search results',
      'Almost ready'
    ];
    
    return messages[Math.floor(Math.random() * messages.length)];
  }
}
