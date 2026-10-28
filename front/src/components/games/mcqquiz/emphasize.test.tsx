import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { emphasize } from './emphasize'

function html(text: string, term: string | null) {
  const { container } = render(<p>{emphasize(text, term)}</p>)
  return container.firstElementChild as HTMLElement
}

describe('emphasize', () => {
  it('bolds the first occurrence of the term, ignoring case', () => {
    const p = html('Ubayy ibn Kaʿb was among the scribes; ubayy ibn kaʿb taught many.', 'Ubayy ibn Kaʿb')
    expect(p.querySelectorAll('b')).toHaveLength(1)
    expect(p.querySelector('b')?.textContent).toBe('Ubayy ibn Kaʿb')
  })

  it('finds an Arabic term whatever its harakat, and keeps the text unchanged', () => {
    const text = 'بنى أبو جعفر المنصور بغدادَ سنة ١٤٥ للهجرة.'
    const p = html(text, 'بغداد')
    expect(p.querySelector('b')?.textContent).toBe('بغدادَ')
    expect(p.textContent).toBe(text)
  })

  it('returns the text as is when the term is absent or too short', () => {
    expect(html('Patience is half of faith.', 'Shukr').querySelector('b')).toBeNull()
    expect(html('A b c', 'a').querySelector('b')).toBeNull()
    expect(html('Some text', null).textContent).toBe('Some text')
  })
})
