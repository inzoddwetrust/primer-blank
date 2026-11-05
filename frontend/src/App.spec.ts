import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import App from './App.vue'
import source from './App.vue?raw'
import { BUILT_IN } from './texts'

const CONFIG = { apiOrigin: 'https://api.example.com', languages: ['en'], defaultLanguage: 'en' }

describe('App', () => {
  it('shows the API origin it was configured with', () => {
    const wrapper = mount(App, {
      props: { config: CONFIG, error: null },
    })
    expect(wrapper.get('[data-test="api-origin"]').text()).toContain('https://api.example.com')
    expect(wrapper.find('[data-test="config-error"]').exists()).toBe(false)
  })

  it('shows the configuration error instead of an origin', () => {
    const wrapper = mount(App, { props: { config: null, error: '/config.json answered 404' } })
    expect(wrapper.get('[data-test="config-error"]').text()).toContain('answered 404')
    expect(wrapper.find('[data-test="api-origin"]').exists()).toBe(false)
  })

  it('says everything in the texts it is given, the built-in ones by default', () => {
    const texts = { title: 'Primer Blank', config_error: 'Settings:', api_label: 'Server:' }
    const given = mount(App, {
      props: { config: CONFIG, error: null, texts },
    })
    expect(given.get('[data-test="title"]').text()).toBe('Primer Blank')
    expect(given.get('[data-test="api-origin"]').text()).toBe('Server: https://api.example.com')
    const failed = mount(App, { props: { config: null, error: 'down', texts } })
    expect(failed.get('[data-test="config-error"]').text()).toBe('Settings: down')
    const builtIn = mount(App, { props: { config: null, error: 'down' } })
    expect(builtIn.get('[data-test="title"]').text()).toBe(BUILT_IN.en?.title)
  })

  it('takes colors, fonts and the logo only from custom properties', () => {
    const style = source.slice(source.indexOf('<style'))
    expect(style).toContain('var(--color-brand-primary)')
    expect(style).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(|url\(/)
  })
})
