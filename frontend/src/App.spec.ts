import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import App from './App.vue'

describe('App', () => {
  it('shows the API origin it was configured with', () => {
    const wrapper = mount(App, {
      props: { config: { apiOrigin: 'https://api.example.com' }, error: null },
    })
    expect(wrapper.get('[data-test="api-origin"]').text()).toContain('https://api.example.com')
    expect(wrapper.find('[data-test="config-error"]').exists()).toBe(false)
  })

  it('shows the configuration error instead of an origin', () => {
    const wrapper = mount(App, { props: { config: null, error: '/config.json answered 404' } })
    expect(wrapper.get('[data-test="config-error"]').text()).toContain('answered 404')
    expect(wrapper.find('[data-test="api-origin"]').exists()).toBe(false)
  })
})
