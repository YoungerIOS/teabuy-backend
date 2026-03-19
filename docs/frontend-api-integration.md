# Teabuy 前后端对接文档（首页/分类/跳转）

适用前端项目：`/Users/chandyoung/Projects.localized/teabuy-hmos`

Base URL:
- 本地：`http://<your-ip>:8000`
- 前缀：`/api/v1`

## 1. 通用约定

### 1.1 统一响应结构
所有接口都返回：

```json
{
  "code": 0,
  "message": "ok",
  "data": {},
  "requestId": "..."
}
```

### 1.2 鉴权
需要登录的接口请带：

```http
Authorization: Bearer <accessToken>
```

### 1.3 错误处理建议
- `40101/40102/40103`：token 无效或过期，前端跳登录页。
- `400xx`：参数错误，提示 message。
- `404xx`：目标资源不存在，提示并停留当前页。

---

## 2. 首页分类模块

## 2.1 获取分类（前台）
- 方法：`GET`
- 路径：`/api/v1/home/categories`
- 鉴权：需要

响应示例：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "title": "分类",
    "items": [
      {
        "key": "tea_bag",
        "name": "袋茶",
        "iconUrl": "https://.../home_review_bg_1.png",
        "linkType": "category",
        "linkValue": "tea_bag",
        "sort": 1
      },
      {
        "key": "teaware",
        "name": "茶具",
        "iconUrl": "https://.../home_review_bg_3.png",
        "linkType": "category",
        "linkValue": "teaware",
        "sort": 3
      }
    ],
    "updatedAt": 0
  },
  "requestId": "..."
}
```

前端处理：
1. 按 `sort` 排序展示。
2. 点击项时不要硬编码跳转，走第 4 节 `navigation/resolve`。

---

## 3. 分类配置（后台 internal）

> 给运营或管理后台使用。普通用户 token 无权限。

## 3.1 获取分类配置
- `GET /api/v1/internal/home/category-config`

## 3.2 更新分类配置
- `PUT /api/v1/internal/home/category-config`

请求体示例：

```json
{
  "title": "分类",
  "items": [
    {
      "key": "tea_bag",
      "name": "袋茶",
      "iconUrl": "https://example.com/tea-bag.png",
      "linkType": "category",
      "linkValue": "tea_bag",
      "sort": 1
    },
    {
      "key": "teaware",
      "name": "茶具",
      "iconUrl": "https://example.com/teaware.png",
      "linkType": "category",
      "linkValue": "teaware",
      "sort": 2
    }
  ]
}
```

---

## 4. 统一跳转解析（强烈建议前端统一走这个接口）

## 4.1 解析入口
- 方法：`GET`
- 路径：`/api/v1/navigation/resolve`
- Query：
  - `linkType`（必填）
  - `linkValue`（可空）

## 4.2 支持类型
- `product`
- `category`
- `activity`
- `review_topic`
- `h5`
- `none`

## 4.3 示例

### product
请求：
`/api/v1/navigation/resolve?linkType=product&linkValue=pnav`

响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "route": "product_detail",
    "params": { "productId": "pnav" }
  }
}
```

### category
请求：
`/api/v1/navigation/resolve?linkType=category&linkValue=teaware`

响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "route": "product_list",
    "params": {
      "categoryKey": "teaware"
    }
  }
}
```

### activity
请求：
`/api/v1/navigation/resolve?linkType=activity&linkValue=flash_sale`

响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "route": "product_list",
    "params": {
      "activityKey": "flash_sale"
    }
  }
}
```

### review_topic
请求：
`/api/v1/navigation/resolve?linkType=review_topic&linkValue=green_tea`

响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "route": "review_list",
    "params": {
      "topicKey": "green_tea"
    }
  }
}
```

### h5
请求：
`/api/v1/navigation/resolve?linkType=h5&linkValue=https%3A%2F%2Fexample.com`

响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "route": "webview",
    "params": {
      "url": "https://example.com"
    }
  }
}
```

---

## 5. 商品列表接口（扩展后）

## 5.1 获取商品列表
- 方法：`GET`
- 路径：`/api/v1/catalog/products`

Query 参数：
- `page`（默认 1）
- `pageSize`（默认 20）
- `category_id`（兼容旧字段）
- `categoryKey`（新）
- `keyword`（新）
- `sort`（新）：`default|sales|priceAsc|priceDesc|newest`
- `priceMin`（新，分）
- `priceMax`（新，分）
- `activityKey`（新）
- `topicKey`（新）

示例：

```http
GET /api/v1/catalog/products?page=1&pageSize=20&categoryKey=teaware&sort=priceAsc&priceMin=1000&priceMax=30000
```

响应示例：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "page": 1,
    "pageSize": 20,
    "items": [
      {
        "id": "p2",
        "name": "玻璃杯",
        "subtitle": "入门茶具",
        "categoryId": "c1",
        "imageUrl": "https://...",
        "priceCent": 2000,
        "priceText": "￥20.00",
        "marketPriceCent": 0,
        "soldCount": 99,
        "badgePrimary": "",
        "badgeSecondary": "",
        "status": "active",
        "stock": 5
      }
    ]
  }
}
```

---

## 6. 前端落地建议（按你们当前路由）

路由参考：`AppRoute`（`product_list`, `product_detail`, `review_list` 等）

点击行为统一流程：
1. UI 元素拿到 `linkType/linkValue`。
2. 调 `GET /navigation/resolve`。
3. 根据返回 `route + params` 调用 `NavService.go(...)` 并透传参数。

这样做的好处：
- 轮播图、分类、推荐卡片都能复用一个点击逻辑。
- 运营改跳转目标不需要前端发版。

---

## 7. cURL 快速联调

```bash
# 1) categories
curl -H "Authorization: Bearer <token>" \
  "http://127.0.0.1:8000/api/v1/home/categories"

# 2) resolve
curl "http://127.0.0.1:8000/api/v1/navigation/resolve?linkType=category&linkValue=teaware"

# 3) products
curl "http://127.0.0.1:8000/api/v1/catalog/products?categoryKey=teaware&sort=priceAsc&page=1&pageSize=20"
```

---

## 8. 当前已实现状态
- [x] `/home/categories`
- [x] `/internal/home/category-config`（GET/PUT）
- [x] `/navigation/resolve`
- [x] `/catalog/products` 扩展筛选参数

