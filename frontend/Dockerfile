# ============================================
# 前端生产镜像（Nginx托管）
# ============================================

# 阶段1：构建
FROM node:20-alpine as builder

WORKDIR /app

# 复制依赖
COPY package.json package-lock.json* ./
RUN npm ci

# 复制源码并构建
COPY . .
RUN npm run build

# 阶段2：Nginx托管
FROM nginx:alpine

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制Nginx配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]