import { defineShikiSetup } from '@slidev/types'

// VS Code's actual "Light+" syntax theme for all code blocks.
export default defineShikiSetup(() => {
  return {
    themes: {
      dark: 'light-plus',
      light: 'light-plus',
    },
  }
})
