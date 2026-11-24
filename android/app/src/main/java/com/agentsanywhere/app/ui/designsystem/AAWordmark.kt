package com.agentsanywhere.app.ui.designsystem

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.TextUnit

@Composable
fun AAWordmark(
    modifier: Modifier = Modifier,
    color: Color = LocalAAColors.current.ink,
    fontSize: TextUnit,
    lineHeight: TextUnit,
    textAlign: TextAlign? = null,
) {
    Text(
        text = "云大师",
        modifier = modifier,
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
