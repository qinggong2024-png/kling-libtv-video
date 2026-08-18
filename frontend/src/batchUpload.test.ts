import { describe, expect, it } from 'vitest'
import { groupBatchUploadFiles } from './batchUpload'

const file = (name: string) => new File(['image'], name, { type: 'image/jpeg' })

describe('groupBatchUploadFiles', () => {
  it('groups one product with ordered storyboards', () => {
    const result = groupBatchUploadFiles([
      file('sku-01_s02.jpg'), file('sku-01_product.jpg'), file('sku-01_s01.jpg'), file('sku-01_s04.jpg'), file('sku-01_s03.jpg'),
    ])
    expect(result.rejected).toEqual([])
    expect(result.groups[0].key).toBe('sku-01')
    expect(result.groups[0].productFront?.name).toBe('sku-01_product.jpg')
    expect(result.groups[0].storyboards.map((item) => item.name)).toEqual(['sku-01_s01.jpg', 'sku-01_s02.jpg', 'sku-01_s03.jpg', 'sku-01_s04.jpg'])
  })

  it('reports missing or invalid files instead of guessing', () => {
    const result = groupBatchUploadFiles([file('sku_s01.jpg'), file('notes.txt')])
    expect(result.rejected).toEqual(['notes.txt'])
    expect(result.groups[0].errors).toContain('缺少“品牌款号正”产品正面图')
  })

  it('supports branded parenthesized storyboards with front and back product images', () => {
    const result = groupBatchUploadFiles([
      file('pw1(2).jpg'), file('pw1背.jpg'), file('pw2(1).jpg'), file('pw1(1).jpg'), file('pw1正.jpg'), file('pw2正.jpg'),
    ])
    expect(result.rejected).toEqual([])
    expect(result.groups.map((group) => group.key)).toEqual(['pw1', 'pw2'])
    expect(result.groups[0].productFront?.name).toBe('pw1正.jpg')
    expect(result.groups[0].productBack?.name).toBe('pw1背.jpg')
    expect(result.groups[0].storyboards.map((item) => item.name)).toEqual(['pw1(1).jpg', 'pw1(2).jpg'])
    expect(result.groups[1].errors).toEqual([])
  })

  it('accepts mixed JPG, PNG, and WEBP files in one group', () => {
    const result = groupBatchUploadFiles([
      file('pw1正.png'), file('pw1背.webp'), file('pw1(1).jpg'), file('pw1(2).png'), file('pw1(3).webp'),
    ])
    expect(result.rejected).toEqual([])
    expect(result.groups[0].productFront?.name).toBe('pw1正.png')
    expect(result.groups[0].productBack?.name).toBe('pw1背.webp')
    expect(result.groups[0].storyboards.map((item) => item.name)).toEqual(['pw1(1).jpg', 'pw1(2).png', 'pw1(3).webp'])
  })

  it('recognizes bounded fuzzy naming variants', () => {
    const result = groupBatchUploadFiles([
      file('pw1 前.png'), file('pw1-后.webp'), file('pw1（1）.jpg'), file('pw1_2.png'), file('pw1第 三 张.webp'),
    ])
    expect(result.rejected).toEqual([])
    expect(result.groups[0].key).toBe('pw1')
    expect(result.groups[0].productFront?.name).toBe('pw1 前.png')
    expect(result.groups[0].productBack?.name).toBe('pw1-后.webp')
    expect(result.groups[0].storyboards.map((item) => item.name)).toEqual(['pw1（1）.jpg', 'pw1_2.png', 'pw1第 三 张.webp'])
  })

  it('rejects ambiguous names and reports duplicate inferred orders', () => {
    const result = groupBatchUploadFiles([
      file('pw11.jpg'), file('pw1正.jpg'), file('pw1(1).jpg'), file('pw1-1.jpg'),
    ])
    expect(result.rejected).toEqual(['pw11.jpg'])
    expect(result.groups[0].errors[0]).toContain('分镜序号 1 重复')
  })
})
