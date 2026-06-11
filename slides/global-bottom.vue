<script setup lang="ts">
import { useNav } from '@slidev/client'
const nav = useNav()
</script>

<template>
  <!-- VS Code status bar — rendered on every slide -->
  <footer class="vscode-statusbar">
    <div class="side">
      <span class="item">&#x2387;&nbsp;main</span>
      <span class="item">licensing-mcp</span>
    </div>
    <div class="side">
      <span class="item">Python 3.13 · MCP 1.27.2</span>
      <span class="item">Ln {{ nav.currentPage.value }}, Col 1</span>
      <span class="item">{{ nav.currentPage.value }} / {{ nav.total.value }}</span>
    </div>
  </footer>
</template>

<style scoped>
.vscode-statusbar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 24px;
  background: #007acc;
  color: #ffffff;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 12px;
  padding: 0 10px;
  z-index: 100;
}
.side {
  display: flex;
  gap: 14px;
}
.item {
  display: inline-flex;
  align-items: center;
  white-space: nowrap;
}
.codicon {
  font-size: 12px;
}
</style>
