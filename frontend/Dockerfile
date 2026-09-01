FROM node:22-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_DEEPSEEK_MODEL=deepseek-v4-flash
ARG NEXT_PUBLIC_KIMI_MODEL=kimi-k2.6
ARG NEXT_PUBLIC_SEVNX_MODEL=gpt-5.5
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_DEEPSEEK_MODEL=$NEXT_PUBLIC_DEEPSEEK_MODEL \
    NEXT_PUBLIC_KIMI_MODEL=$NEXT_PUBLIC_KIMI_MODEL \
    NEXT_PUBLIC_SEVNX_MODEL=$NEXT_PUBLIC_SEVNX_MODEL
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=7878
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 7878
CMD ["node", "server.js"]
