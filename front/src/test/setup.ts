import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'
import '@testing-library/jest-dom/vitest'

// Node >= 25 ships its own Web Storage globals. Without --localstorage-file its
// `localStorage` getter returns undefined, and because it already exists on the
// global object it shadows happy-dom's implementation: every test touching auth
// storage failed with "Cannot read properties of undefined". Install an in-memory
// Storage when that happens, so the suite behaves the same on every Node version.
class MemoryStorage implements Storage {
  private items = new Map<string, string>()
  get length() {
    return this.items.size
  }
  clear() {
    this.items.clear()
  }
  getItem(key: string) {
    return this.items.has(key) ? (this.items.get(key) as string) : null
  }
  key(index: number) {
    return [...this.items.keys()][index] ?? null
  }
  removeItem(key: string) {
    this.items.delete(key)
  }
  setItem(key: string, value: string) {
    this.items.set(key, String(value))
  }
}

if (typeof globalThis.localStorage === 'undefined') {
  Object.defineProperty(globalThis, 'localStorage', { value: new MemoryStorage(), configurable: true, writable: true })
}

// Ensure DOM cleanup after each test (happy-dom does not auto-cleanup)
afterEach(() => {
  cleanup()
})

// Mock react-i18next to return keys as translations
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
  Trans: ({ children }: { children: React.ReactNode }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
