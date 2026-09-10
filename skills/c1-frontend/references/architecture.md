# 架构与维护边界

新项目默认使用 React、TypeScript、Vite、Tailwind CSS 4 和基于 Base UI 的 shadcn/ui。已有项目只在任务授权的范围内调整架构。

## 职责与依赖

```text
产品任务 → 页面与业务组件 → 状态、数据规则与 API
               ↓
         项目自有 UI 组件 → Base UI / 原生 HTML
               ↑
情绪板 → 语义主题 token → Tailwind / 业务 CSS
```

页面决定用户如何完成工作，基础组件提供稳定的交互和视觉契约。主题改变表达，不改变权限、保存、执行与完成的含义。

以下是按职责组织的示意；按现有项目规模合并或拆分，不为符合目录图创建空层：

```text
src/
  app/                   # 应用壳、入口、全局 provider
  features/<feature>/    # 页面、业务组件、该功能的状态与请求
  components/ui/         # 项目拥有的 shadcn 组件及共享变体
  lib/                   # cn 等无业务工具
  styles/
    theme.css            # 颜色、字体、形状及 Tailwind 语义映射
    globals.css          # 样式入口、基础排版和全局约定
```

状态默认从 React Hooks 和必要的 Context 起步；跨页面 URL、服务端缓存或复杂共享状态出现真实需求后，再选择相应工具。不要把 Constx 的编辑器、认证、事件订阅、Rust 服务和静态资源嵌入链路复制成所有项目的依赖。

## shadcn 与 Base UI

- 初始化时明确选择 **Base UI**。蓝本中的 `base-nova` 是其当时的生成风格；它可作为紧凑起点，不能代替本 Skill 的最终 token 与组件规范，也不应假定未来 CLI 始终使用同一名字。
- 核对 `components.json`、生成组件的 import 和锁文件，确认交互依赖为 `@base-ui/react`。`baseColor: neutral` 只是初始配色选择，不妨碍使用独立品牌色。
- 基础组件源码归项目维护。更新或添加组件前查看本地修改，避免生成器覆盖已确认的变体和交互。
- Base UI 的元素组合使用其实际 `render` API；不要照搬 Radix 的 `asChild`。自定义 render 元素必须把属性和 ref 传到正确的 DOM 节点，保留事件合并与键盘行为。
- 生成器的不同版本可能改变组件结构和依赖。以当前文档与源码为准，不在 Skill 中锁死整套生成命令。

当前搭配已通过 [shadcn 的 Vite 文档](https://ui.shadcn.com/docs/installation/vite)、[主题文档](https://ui.shadcn.com/docs/theming)及 [Base UI 组合文档](https://base-ui.com/react/handbook/composition)核对（2026-09-10）。实施时再次核对版本相关部分。

## 样式与主题

Tailwind 负责 utility、响应式与状态选择器，CVA 负责共享组件的 variant 和 size。复杂编辑器、文档排版和工作区布局可以使用普通 CSS；两者消费同一套语义变量。

Tailwind 4 的 Vite 集成使用 `@tailwindcss/vite`，CSS 入口使用 `@import "tailwindcss"`。通过 `@theme inline` 把运行时变量映射到 utility，避免把一套品牌值分别维护在 CSS 与 Tailwind 配置中。

下面仅示意主题映射方式；全量角色取值见 [情绪板](mood-board.md)。路径、导入顺序和其他角色按项目补齐：

```css
@import "tailwindcss";

:root {
  --background: #fbfbf9;
  --foreground: #22241f;
  --primary: #22241f;
  --primary-foreground: #fbfbf9;
  --border: #dfe1d9;
  --input: #898e82;
  --ring: #2458a6;
}

.dark {
  --background: #20221e;
  --foreground: #edeee8;
  --primary: #e7ebdf;
  --primary-foreground: #22241f;
  --border: #3c4037;
  --input: #727a66;
  --ring: #a5c2ff;
}

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);
}
```

使用 `bg-background text-foreground`、`bg-primary text-primary-foreground`、`border-input` 等语义组合。普通分隔线的 `border` 比输入边界浅，不要混用。HEX 是原材料的精确色样；若项目使用 OKLCH，做等值转换后维护单一来源，不因颜色格式改变已确定的气质。

局部页面可以控制布局；公共颜色、字体、形状与交互尺寸集中维护。相同差异重复出现时提取 variant，不为单个页面搭建庞大的组件封装。

## 主题、状态与交付

- 外观偏好默认支持 system / light / dark，跟随系统作为初始选择；已有产品的偏好入口继续保留。主题切换在根节点生效，并覆盖 portal 中的菜单、弹窗与提示。
- 为背景、文字、输入边界、焦点和状态分别维护语义；深色主题重新分配亮度，不简单反色。
- 响应式调整展示关系时，把草稿和业务状态放在不会随面板卸载而丢失的位置，或者保留必要面板挂载。不能仅靠隐藏 CSS 宣称状态已保持。
- 构建产物、资源基路径、API 边界与部署宿主按项目确定。Vite 静态构建通过，不代表远端部署或真实服务链路已通过。
