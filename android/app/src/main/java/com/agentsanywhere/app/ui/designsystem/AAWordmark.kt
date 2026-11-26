package com.agentsanywhere.app.ui.designsystem

import androidx.compose.material3.Text
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.size
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import com.agentsanywhere.app.R
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.TextUnit

/** 展示统一云朵品牌图标与应用名称，图标随文字尺寸缩放。 */
@Composable
fun AAWordmark(
    modifier: Modifier = Modifier,
    color: Color = LocalAAColors.current.ink,
    fontSize: TextUnit,
    lineHeight: TextUnit,
    textAlign: TextAlign? = null,
) {
    Row(
        modifier = modifier,
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = if (textAlign == TextAlign.Center) Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally) else Arrangement.spacedBy(8.dp),
    ) {
        Image(
            painter = painterResource(R.drawable.yundashi_logo),
            contentDescription = null,
            modifier = Modifier.size(with(LocalDensity.current) { fontSize.toDp() }),
        )
        Text(
            text = "云大师Agent",
            color = color,
            fontSize = fontSize,
            fontFamily = FontFamily.Default,
            fontWeight = FontWeight.Medium,
            lineHeight = lineHeight,
            letterSpacing = TextUnit.Unspecified,
            textAlign = textAlign,
            maxLines = 1,
        )
    }
}
