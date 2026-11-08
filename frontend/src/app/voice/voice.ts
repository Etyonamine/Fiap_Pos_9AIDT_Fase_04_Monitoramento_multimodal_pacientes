import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-voice',
  imports: [RouterLink],
  templateUrl: './voice.html',
  styleUrl: './voice.scss',
})
export class Voice {
  protected readonly waveBars = [16, 28, 44, 32, 62, 82, 58, 38, 72, 96, 68, 46, 78, 56, 34, 64, 86, 52, 30, 48, 24, 16];
}
