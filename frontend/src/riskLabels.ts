const riskFlagLabels: Record<string, string> = {
  TEXT_OR_LOGO_KEY_SELLING_POINT: '服装文字或品牌标识是关键卖点，生成时可能失真',
  GARMENT_PARTIALLY_OCCLUDED: '服装被遮挡，部分细节可能无法准确还原',
  STORYBOARD_GARMENT_CONFLICT: '模特场景图与产品图中的服装不一致，款式、颜色、图案或细节可能偏差',
  STORYBOARD_IDENTITY_CONFLICT: '不同参考图中的模特身份不一致，人物外观可能发生变化',
  MULTIPLE_PEOPLE: '参考图中有多个人物，主体识别可能不稳定',
  BACK_VIEW_REQUIRED: '需要展示服装背面，但背面参考信息不足',
  LOW_DETAIL_REFERENCE: '参考图细节不足，面料、印花或标识可能无法准确还原',
  LARGE_POSE_CHANGE: '人物姿势变化较大，动作衔接可能不自然',
  SCENE_DISCONTINUITY: '参考图场景不连续，镜头切换可能出现环境变化',
}

export function formatRiskFlags(risks: string[]): string {
  return risks.map((risk) => riskFlagLabels[risk] ?? risk).join('、')
}
