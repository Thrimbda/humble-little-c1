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

## shadcn 与 Base UI

使用 shadcn/ui 的 **Base UI 版本**，交互原语采用 `@base-ui/react`。组件源码由项目维护，外观、尺寸与变体遵循本 Skill 的情绪板和组件规范。

技术文档：[shadcn 的 Vite 集成](https://ui.shadcn.com/docs/installation/vite)、[主题](https://ui.shadcn.com/docs/theming)与 [Base UI 组件组合](https://base-ui.com/react/handbook/composition)。

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

使用 `bg-background text-foreground`、`bg-primary text-primary-foreground`、`border-input` 等语义组合。普通分隔线的 `border` 比输入边界浅，不要混用。

局部页面可以控制布局；公共颜色、字体、形状与交互尺寸集中维护。相同差异重复出现时提取 variant，不为单个页面搭建庞大的组件封装。

## 主题、状态与交付

- 外观偏好默认支持 system / light / dark，跟随系统作为初始选择；已有产品的偏好入口继续保留。主题切换在根节点生效，并覆盖 portal 中的菜单、弹窗与提示。
- 为背景、文字、输入边界、焦点和状态分别维护语义；深色主题重新分配亮度，不简单反色。
- 响应式调整展示关系时，把草稿和业务状态放在不会随面板卸载而丢失的位置，或者保留必要面板挂载。不能仅靠隐藏 CSS 宣称状态已保持。
- 构建产物、资源基路径、API 边界与部署宿主按项目确定。Vite 静态构建通过，不代表远端部署或真实服务链路已通过。
