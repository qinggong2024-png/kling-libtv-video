import { describe, expect, it } from 'vitest'

import { createImageCenterVideoSeed } from './imageCenterVideoSeed'

function image(name: string): File {
  return new File(['image'], name, { type: 'image/jpeg' })
}

describe('image center video seed', () => {
  it('hands off selected images without carrying image prompts into video production', () => {
    const productFront = image('product-front.jpg')
    const productBack = image('product-back.jpg')
    const storyboard = image('storyboard.jpg')
    const seed = createImageCenterVideoSeed(
      { product: { front: productFront, back: productBack, side: null } },
      [storyboard],
      ['output-1'],
      productFront,
      'video-seed',
    )

    expect(seed).toEqual({
      id: 'video-seed',
      storyboards: [storyboard],
      storyboardOutputIds: ['output-1'],
      products: [productFront, productBack],
      subjectFiles: {
        frontalImage: productFront,
        backImage: null,
        detailImages: [],
      },
    })
    expect(seed).not.toHaveProperty('requirement')
    expect(seed).not.toHaveProperty('prompt')
  })
})
