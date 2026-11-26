// src/types.ts → window.RPTypes
// All shared TypeScript interfaces for the roleplay app

(function() {
  // This file defines types. Since we're in browser Babel, we just export the namespace.
  // Types are used for intellisense/documentation purposes in browser Babel mode.
  // Runtime values (enums, constants) are what get exported.

  window.RPTypes = {
    // Enum-like constants
    TurnStage: {
      VALIDATING: 'validating',
      GENERATING: 'generating',
      NARRATING: 'narrating',
      COMPLETED: 'completed',
      BLOCKED: 'blocked',
      FAILED: 'failed',
    },
    MessageRole: {
      USER: 'user',
      ASSISTANT: 'assistant',
      DIRECTOR: 'director',
      SYSTEM: 'system',
    },
    WsEventType: {
      TURN_ACCEPTED: 'turn_accepted',
      STATE_CHANGE: 'state_change',
      TEXT_CHUNK: 'text_chunk',
      MESSAGE_COMPLETED: 'message_completed',
      ENGINE_STATE_UPDATED: 'engine_state_updated',
      DIRECTOR_STATE_CHANGE: 'director_state_change',
      ACTION_BLOCKED: 'action_blocked',
      ERROR: 'error',
      PING: 'ping',
      PONG: 'pong',
    },
  };
})();

/*
TypeScript Interface Definitions (for reference — Babel strips these at runtime):

interface User {
  id: string;
  username: string;
  api_key?: string;
}

interface Session {
  userId: string;
  username: string;
  apiKey: string;
}

interface Character {
  id: string;
  scenario_id: string;
  name: string;
  gender?: string;
  age?: string;
  personality?: string;
  likes?: string[];
  dislikes?: string[];
  backstory?: string;
  example_dialogue?: string;
  appearance?: string;
  greeting?: string;
  role_description?: string;
  is_ai: boolean;
  created_at: string;
  updated_at: string;
}

interface Lore {
  id: string;
  scenario_id: string;
  keyword: string;
  description: string;
  category?: string;
  created_at: string;
}

interface Scenario {
  id: string;
  title: string;
  greeting?: string;
  place?: string;
  time?: string;
  introduction?: string;
  is_public: boolean;
  published_at?: string;
  created_at: string;
  updated_at: string;
  cast?: Character[];
  lore?: Lore[];
  rules?: any;
  initial_state?: any;
}

interface CatalogScenario {
  id: string;
  title: string;
  place?: string;
  time?: string;
  introduction?: string;
  cast?: Character[];
  published_at: string;
}

interface Conversation {
  id: string;
  title?: string;
  status: string;
  archived: boolean;
  scenario_id: string;
  parent_conversation_id?: string;
  created_at: string;
  updated_at: string;
}

interface Message {
  id: string;
  conversation_id: string;
  turn_id?: string;
  role: 'user' | 'assistant' | 'director' | 'system';
  content: string;
  generation_id?: string;
  attempt?: number;
  created_at: string;
  is_provisional?: boolean;
  request_id?: string;
}

interface Turn {
  id: string;
  conversation_id: string;
  status: string;
  stage?: string;
  blocked_reason?: string;
  created_at: string;
  updated_at: string;
}

interface TurnStage {
  VALIDATING: 'validating';
  GENERATING: 'generating';
  NARRATING: 'narrating';
  COMPLETED: 'completed';
  BLOCKED: 'blocked';
  FAILED: 'failed';
}

interface InventoryItem {
  name: string;
  description?: string;
  quantity: number;
}

interface Relationship {
  character_id?: string;
  character_name: string;
  relationship_status?: string;
  affinity_score: number;
}

interface QuestStage {
  id: string;
  description: string;
  completed: boolean;
}

interface QuestProgress {
  quest_id: string;
  title: string;
  status: string;
  stages: QuestStage[];
}

interface GameState {
  place?: string;
  time?: string;
  inventory?: InventoryItem[];
  relationships?: Relationship[];
  quests?: QuestProgress[];
  [key: string]: any;
}

interface ConversationResume {
  conversation: Conversation;
  messages: Message[];
  game_state?: GameState;
  active_turn?: Turn;
  last_seen_seq?: number;
}

interface Preferences {
  language?: string;
  response_length?: 'short' | 'medium' | 'long';
  perspective?: 'first' | 'third';
  pacing?: 'slow' | 'balanced' | 'fast';
  formatting?: 'asterisks' | 'plain';
  intensity?: 'gentle' | 'balanced' | 'dramatic';
}

interface Persona {
  id: string;
  name: string;
  background?: string;
  personality?: string;
  appearance?: string;
  created_at: string;
  updated_at: string;
}

interface Memory {
  id: string;
  conversation_id: string;
  content: string;
  pinned: boolean;
  forgotten: boolean;
  known_by: string[];
  created_at: string;
}

interface MemoryNote {
  id: string;
  conversation_id: string;
  content: string;
  pinned: boolean;
  created_at: string;
}

interface WsFrame {
  type: string;
  seq?: number;
  data?: any;
}

interface WsEventBody {
  turn_id?: string;
  generation_id?: string;
  attempt?: number;
  stage?: string;
  chunk?: string;
  chunk_index?: number;
  message_id?: string;
  content?: string;
  role?: string;
  game_state?: GameState;
  blocked_reason?: string;
  request_id?: string;
}
*/
