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
    expect(result.groups[0].product?.name).toBe('sku-01_product.jpg')
    expect(result.groups[0].storyboards.map((item) => item.name)).toEqual(['sku-01_s01.jpg', 'sku-01_s02.jpg', 'sku-01_s03.jpg', 'sku-01_s04.jpg'])
  })

  it('reports missing or invalid files instead of guessing', () => {
    const result = groupBatchUploadFiles([file('sku_s01.jpg'), file('notes.txt')])
    expect(result.rejected).toEqual(['notes.txt'])
    expect(result.groups[0].errors).toContain('缺少 *_product 产品图')
  })
})
